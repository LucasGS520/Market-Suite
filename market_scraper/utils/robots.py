""" Utilitário centralizado para respeito ao robots.txt antes de scraping """

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from urllib import robotparser
from urllib.parse import urlparse

import structlog

from shared.metrics.metrics_scraper import SCRAPER_ROBOTS_CHECK_TOTAL


logger = structlog.get_logger(__name__)

#TTL padrão em segundos para reutilização de robots.txt por host
_CACHE_TTL_SECONDS = 3600  #1 hora

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

def _get_parser(host: str, robots_url: str) -> robotparser.RobotFileParser | None:
    """ Obtém parser do cache ou realiza download do robots.txt do host """
    now = time.monotonic()
    with _CACHE_LOCK:
        entry = _ROBOTS_CACHE.get(host)
        if entry and entry.expires_at > now:
            return entry.parser
        if entry and entry.expires_at <= now:
            _ROBOTS_CACHE.pop(host, None)

    parser = robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        #Mantemos leitura direta pois urllib já lida com caching básico HTTP
        parser.read()
    except Exception as exc:
        logger.warning(
            "robots_fetch_error",
            host=host,
            robots_url=robots_url,
            error=str(exc),
        )
        return None
    
    expires_at = time.monotonic() + _CACHE_TTL_SECONDS
    with _CACHE_LOCK:
        _ROBOTS_CACHE[host] = _RobotsCacheEntry(parser=parser, expires_at=expires_at)
    return parser

def is_allowed(url: str, user_agent: str = "marketsuite-scraper") -> bool:
    """ Retorna ``True`` quando o robots.txt autoriza o user-agent para a URL """
    normalized_url, robots_url, host_key = _prepare_urls(url)
    parser = _get_parser(host_key, robots_url)

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
