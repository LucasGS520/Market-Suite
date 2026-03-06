""" Utilitário centralizado para respeito ao robots.txt antes de scraping

O módulo valida o acesso com ``robots.txt`` de forma assíncrona reaproveitando
limites de rede definidos nas configurações globais. O cache Redis compartilhado
reduz round-trips desnecessários entre instâncias do scraper. A política de
fallback é restritiva para impedir acessos quando o arquivo não pode ser
validado, privilegiando conformidade legal.

Cache:
  Redis (chave ``robots:{host}``, TTL 3600s) — compartilhado entre workers.
  Armazena o texto bruto do robots.txt; o parser é reconstruído em memória.
  Fallback: se Redis indisponível, realiza download direto.
"""

from __future__ import annotations

from urllib import robotparser
from urllib.parse import urlparse

import httpx
import structlog

from shared.utils.logging_utils import sanitize_log_data
from shared.utils.redis_client import get_redis_client
from shared.enums.cache_keys import CacheKey

from market_scraper.utils.http_retry import (
    RetryableHTTPError,
    build_retrying_operation,
)
from market_scraper.utils.http_utils import build_timeout
from market_scraper.core.config_scraper import settings


logger = structlog.get_logger(__name__)

#TTL do cache Redis para robots.txt (1 hora, alinhado com REDIS_TTL_ROBOTS_CACHE_SECONDS)
_ROBOTS_REDIS_TTL = 3600

#Cabeçalho padrão para leitura de robots respeitando a identificação do serviço
_ROBOTS_HEADERS = {
    "User-Agent": "marketsuite-scraper/1.0",
    "Accept": "text/plain",
}

def _prepare_urls(url: str) -> tuple[str, str, str]:
    """ Normaliza a URL recebida e retorna informações úteis para o cache """
    cleaned = (url or "").strip()
    if not cleaned:
        raise ValueError("URL vazia ou inválida para verificação de robots.txt")
    
    parsed = urlparse(cleaned, scheme="https")
    if not parsed.netloc:
        parsed = urlparse(f"https://{cleaned}")
    if not parsed.netloc:
        raise ValueError("URL vazia ou inválida para verificação de robots.txt")
    
    scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "https"
    normalized_url = parsed._replace(scheme=scheme).geturl()
    robots_url = f"{scheme}://{parsed.netloc}/robots.txt"
    host_key = parsed.netloc.lower()
    return normalized_url, robots_url, host_key

async def _download_robots(robots_url: str, *, timeout: float) -> str | None:
    """ Baixa o conteúdo do robots.txt respeitando limites configurados """
    client_timeout = build_timeout(timeout)
    limits = httpx.Limits(
        max_connections=settings.SCRAPER_HTTP_MAX_CONNECTIONS,
        max_keepalive_connections=settings.SCRAPER_HTTP_MAX_KEEPALIVE,
    )
 
    async def _execute_request() -> httpx.Response:
        async with httpx.AsyncClient(
            timeout=client_timeout,
            follow_redirects=True,
            limits=limits,
            max_redirects=settings.SCRAPER_HTTP_MAX_REDIRECTS,
        ) as client:
            return await client.get(robots_url, headers=_ROBOTS_HEADERS)
        
    wrapped_operation = build_retrying_operation(
        target="robots",
        operation=_execute_request,
    )

    try:
        response = await wrapped_operation()
    except RetryableHTTPError as exc:
        logger.warning(
            "robots_fetch_retry_exhausted",
            robots_url=sanitize_log_data(robots_url),
            reason=exc.reason,
        )
        original = exc.__cause__
        if original is not None:
            logger.warning(
                "robots_fetch_error", #Mantém label clássico para análise interna
                robots_url=sanitize_log_data(robots_url),
                error=str(original),
            )
        return None
    except httpx.HTTPError as exc:
        logger.warning(
            "robots_fetch_error",
            robots_url=sanitize_log_data(robots_url),
            error=str(exc),
        )
        return None
    
    content = response.content
    if len(content) > settings.SCRAPER_HTTP_MAX_CONTENT_LENGTH:
        #Protege contra payloads anormalmente grandes
        logger.warning(
            "robots_fetch_too_large",
            robots_url=sanitize_log_data(robots_url),
            size=len(content),
            max_size=settings.SCRAPER_HTTP_MAX_CONTENT_LENGTH,
        )
        return None
    
    if response.status_code >= 400:
        #Conteúdos inexistentes equivalem à ausência de restrições públicas
        return ""
    
    return response.text

def _build_parser(
    robots_url: str,
    text: str,
    *,
    host: str,
) -> robotparser.RobotFileParser | None:
    """ Constrói RobotFileParser a partir do texto bruto """
    parser = robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.parse(text.splitlines())
    except Exception as exc:
        logger.warning(
            "robots_parse_error",
            host=host,
            robots_url=robots_url,
            error=str(exc),
        )
        return None
    return parser

async def _get_parser(
    host: str,
    robots_url: str,
    *,
    timeout: float,
) -> robotparser.RobotFileParser | None:
    """ Obtém parser do cache Redis ou realiza download assíncrono do robots.txt.

    Fluxo:
      1. Tenta ler texto do Redis (chave ``robots:{host}``)
      2. Se hit: reconstrói parser em memória (sem I/O de rede)
      3. Se miss ou Redis indisponível: download HTTP → armazena no Redis → retorna parser
    """
    cache_key = CacheKey.robots_txt(host)

    #Tentativa de cache Redis
    try:
        client = get_redis_client()
        cached_text = client.get(cache_key)
        if cached_text is not None:
            logger.debug("robots_cache_hit", host=host)
            return _build_parser(robots_url, cached_text, host=host)
    except Exception as exc:
        logger.warning("robots_cache_get_failed", host=host, error=str(exc))

    #Cache miss: download HTTP
    text = await _download_robots(robots_url, timeout=timeout)
    if text is None:
        return None

    parser = _build_parser(robots_url, text, host=host)
    if parser is None:
        return None

    #Persiste no Redis com TTL
    try:
        client = get_redis_client()
        client.setex(cache_key, _ROBOTS_REDIS_TTL, text)
        logger.debug("robots_cache_populated", host=host, ttl=_ROBOTS_REDIS_TTL)
    except Exception as exc:
        logger.warning("robots_cache_set_failed", host=host, error=str(exc))

    return parser

async def is_allowed(
    url: str,
    user_agent: str = "marketsuite-scraper",
    *,
    timeout: float | None = None,
) -> bool:
    """ Retorna ``True`` quando o robots.txt autoriza ou quando fallback permite """
    normalized_url, robots_url, host_key = _prepare_urls(url)
    timeout_value = timeout if timeout is not None else settings.SCRAPER_STEP_TIMEOUT_SECONDS
    parser = await _get_parser(host_key, robots_url, timeout=timeout_value)

    if parser is None:
        #Sem parser confiável, evitamos scraping para cumprir políticas públicas do site
        logger.warning(
            "robots_fallback_block",
            host=host_key,
            url=normalized_url,
            reason="parser_unavailable",
        )
        return False

    try:
        allowed = parser.can_fetch(user_agent, normalized_url)
    except Exception as exc:
        logger.warning(
            "robots_can_fetch_error",
            host=host_key,
            url=normalized_url,
            user_agent=user_agent,
            error=str(exc),
        )
        #Fallback permanece permissivo para garantir disponibilidade do pipeline
        return False
    
    outcome = "allowed" if allowed else "disallowed"

    if not allowed:
        #Registramos no log para facilitar diagnóstico em produção
        logger.info(
            "robots_disallowed",
            host=host_key,
            url=normalized_url,
            user_agent=user_agent,
        )

    return allowed


__all__ = [
    "is_allowed",
]
