""" Utilitário centralizado para respeito ao robots.txt antes de scraping 

O módulo valida o acesso com ``robots.txt`` de forma assíncrona reaproveitando
limites de rede definidos nas configurações globais. O cache interno reduz
round-trips desnecessários enquanto preserva métricas de sucesso e erro.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from urllib import robotparser
from urllib.parse import urlparse

import httpx
import structlog

from market_scraper.core.config_scraper import settings
from shared.metrics.metrics_scraper import SCRAPER_ROBOTS_CHECK_TOTAL
from shared.utils.logging_utils import sanitize_log_data

from market_scraper.utils.http_retry import (
    RetryableHTTPError,
    build_retrying_operation,
)


logger = structlog.get_logger(__name__)

#TTL padrão em segundos para reutilização de robots.txt por host
_CACHE_TTL_SECONDS = 3600  #1 hora

#Cabeçalho padrão para leitura de robots respeitando a identificação do serviço
_ROBOTS_HEADERS = {
    "User-Agent": "marketsuite-scraper/1.0",
    "Accept": "text/plain",
}

@dataclass
class _RobotsCacheEntry:
    """ Representa um robots.txt carregado com expiração pré-definida """
    parser: robotparser.RobotFileParser
    expires_at: float

#Cache protegido por lock para evitar leituras simultâneas redundantes
_ROBOTS_CACHE: dict[str, _RobotsCacheEntry] = {}
_CACHE_LOCK = threading.Lock()

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

def _build_timeout(total_timeout: float) -> httpx.Timeout:
    """ Monta o objeto de timeout alinhado aos limites globais do serviço """
    return httpx.Timeout(
        total_timeout,
        connect=min(total_timeout, settings.SCRAPER_HTTP_TIMEOUT_CONNECT),
        read=min(total_timeout, settings.SCRAPER_HTTP_TIMEOUT_READ),
        write=min(total_timeout, settings.SCRAPER_HTTP_TIMEOUT_WRITE),
        pool=settings.SCRAPER_HTTP_TIMEOUT_POOL,
    )

async def _download_robots(robots_url: str, *, timeout: float) -> str | None:
    """ Baixa o conteúdo do robots.txt respeitando limites configurados """
    client_timeout = _build_timeout(timeout)
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
                "robots_fetch_error", #Mantém label clássico para observabilidade
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

async def _get_parser(
    host: str,
    robots_url: str,
    *,
    timeout: float,
) -> robotparser.RobotFileParser | None:
    """ Obtém parser do cache ou realiza download assíncrono do robots.txt """
    now = time.monotonic()
    with _CACHE_LOCK:
        entry = _ROBOTS_CACHE.get(host)
        if entry and entry.expires_at > now:
            return entry.parser
        if entry and entry.expires_at <= now:
            _ROBOTS_CACHE.pop(host, None)

    text = await _download_robots(robots_url, timeout=timeout)
    if text is None:
        return None

    parser = robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        #Mantemos leitura direta pois urllib já lida com caching básico HTTP
        parser.parse(text.splitlines())
    except Exception as exc:
        logger.warning(
            "robots_parse_error",
            host=host,
            robots_url=robots_url,
            error=str(exc),
        )
        return None
    
    expires_at = time.monotonic() + _CACHE_TTL_SECONDS
    with _CACHE_LOCK:
        _ROBOTS_CACHE[host] = _RobotsCacheEntry(parser=parser, expires_at=expires_at)
    return parser

async def is_allowed(
    url: str,
    user_agent: str = "marketsuite-scraper",
    *,
    timeout: float | None = None,
) -> bool:
    """ Retorna ``True`` quando o robots.txt autoriza o user-agent para a URL """
    normalized_url, robots_url, host_key = _prepare_urls(url)
    timeout_value = timeout if timeout is not None else settings.SCRAPER_STEP_TIMEOUT_SECONDS
    parser = await _get_parser(host_key, robots_url, timeout=timeout_value)

    if parser is None:
        #Em caso de erro optamos por permitir seguindo recomendação do requisito
        SCRAPER_ROBOTS_CHECK_TOTAL.labels(outcome="error").inc()
        return True
    
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
        SCRAPER_ROBOTS_CHECK_TOTAL.labels(outcome="error").inc()
        return True
    
    outcome = "allowed" if allowed else "disallowed"
    SCRAPER_ROBOTS_CHECK_TOTAL.labels(outcome=outcome).inc()

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
