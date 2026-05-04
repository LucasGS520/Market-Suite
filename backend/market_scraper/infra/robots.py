""" Utilitário centralizado para respeito ao robots.txt antes de scraping.

Gerencia o robots.txt com:
    - Cache Redis compartilhado (chave ``robots:{host}``, TTL 3600s)
    - Download HTTP com retry via tenacity (429/5xx)
    - Fallback restritivo: bloqueia quando robots.txt não pode ser validado

Pertence à camada de infra porque depende de Redis, HTTP e retries operacionais.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable
from urllib import robotparser
from urllib.parse import urlparse

import httpx
import structlog
from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt
from tenacity.wait import wait_base

from shared.utils.logging_utils import sanitize_log_data
from shared.utils.redis_client import get_redis_operational
from shared.enums.cache_keys import CacheKey

from market_scraper.utils.http_utils import build_timeout, parse_retry_after
from market_scraper.core.config_scraper import settings


logger = structlog.get_logger(__name__)

_ROBOTS_HEADERS = {
    "User-Agent": "marketsuite-scraper/1.0",
    "Accept": "text/plain",
}
_RETRYABLE_STATUS = {429, *range(500, 600)}


@dataclass
class _RetryableRobotsHTTPError(Exception):
    """ Erro transitório elegível para nova tentativa no download de robots.txt."""

    reason: str
    status_code: int | None = None
    retry_after: float | None = None


def _compute_retry_wait_seconds(*, retry_state: RetryCallState, multiplier: float) -> float:
    attempt_index = max(retry_state.attempt_number - 1, 0)
    base_wait = max(0.0, multiplier) * (2 ** attempt_index)
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, _RetryableRobotsHTTPError) and exc.retry_after is not None:
        return exc.retry_after
    return base_wait


class _WaitRobotsRetryAfter(wait_base):
    """ Combina backoff exponencial simples com prioridade ao Retry-After."""

    def __init__(self, *, multiplier: float) -> None:
        self._multiplier = multiplier

    def __call__(self, retry_state: RetryCallState) -> float:
        return _compute_retry_wait_seconds(
            retry_state=retry_state,
            multiplier=self._multiplier,
        )


def _categorize_retry_reason(status_code: int | None) -> str:
    if status_code == 429:
        return "too_many_requests"
    if status_code is not None and 500 <= status_code < 600:
        return "server_error"
    return "network_error"


def _before_robots_retry_sleep(retry_state: RetryCallState) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if not isinstance(exc, _RetryableRobotsHTTPError):
        return
    wait_seconds = _compute_retry_wait_seconds(
        retry_state=retry_state,
        multiplier=max(0.0, settings.SCRAPER_HTTP_RETRY_BACKOFF_BASE),
    )
    logger.warning(
        "http_retry_scheduled",
        target="robots",
        reason=exc.reason,
        wait_seconds=wait_seconds,
    )


def _raise_for_retryable_robots_response(response: httpx.Response) -> None:
    if response.status_code not in _RETRYABLE_STATUS:
        return
    retry_after = parse_retry_after(response.headers.get("Retry-After"))
    reason = _categorize_retry_reason(response.status_code)
    exc = httpx.HTTPStatusError(
        "Download HTTP elegível para nova tentativa",
        request=response.request,
        response=response,
    )
    raise _RetryableRobotsHTTPError(
        reason=reason,
        status_code=response.status_code,
        retry_after=retry_after,
    ) from exc


def _build_robots_retrying_operation(
    operation: Callable[[], Awaitable[httpx.Response]],
) -> Callable[[], Awaitable[httpx.Response]]:
    attempts = max(1, settings.SCRAPER_HTTP_RETRIES + 1)
    wait_strategy = _WaitRobotsRetryAfter(
        multiplier=max(0.0, settings.SCRAPER_HTTP_RETRY_BACKOFF_BASE),
    )

    @retry(
        retry=retry_if_exception_type(_RetryableRobotsHTTPError),
        stop=stop_after_attempt(attempts),
        wait=wait_strategy,
        before_sleep=_before_robots_retry_sleep,
        reraise=True,
    )
    async def _wrapped_operation() -> httpx.Response:
        try:
            response = await operation()
        except httpx.RequestError as exc:
            raise _RetryableRobotsHTTPError(
                reason=_categorize_retry_reason(None),
            ) from exc

        _raise_for_retryable_robots_response(response)
        return response

    return _wrapped_operation


def _prepare_urls(url: str) -> tuple[str, str, str]:
    """ Normaliza a URL recebida e retorna informações úteis para o cache."""
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
    """ Baixa o conteúdo do robots.txt respeitando limites configurados."""
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

    wrapped_operation = _build_robots_retrying_operation(_execute_request)

    try:
        response = await wrapped_operation()
    except _RetryableRobotsHTTPError as exc:
        logger.warning(
            "robots_fetch_retry_exhausted",
            robots_url=sanitize_log_data(robots_url),
            reason=exc.reason,
        )
        original = exc.__cause__
        if original is not None:
            logger.warning(
                "robots_fetch_error",
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
        logger.warning(
            "robots_fetch_too_large",
            robots_url=sanitize_log_data(robots_url),
            size=len(content),
            max_size=settings.SCRAPER_HTTP_MAX_CONTENT_LENGTH,
        )
        return None

    if response.status_code >= 400:
        return ""

    return response.text


def _build_parser(
    robots_url: str,
    text: str,
    *,
    host: str,
) -> robotparser.RobotFileParser | None:
    """ Constrói RobotFileParser a partir do texto bruto."""
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

    try:
        client = get_redis_operational()
        cached_text = client.get(cache_key)
        if cached_text is not None:
            logger.debug("robots_cache_hit", host=host)
            return _build_parser(robots_url, cached_text, host=host)
    except Exception as exc:
        logger.warning("robots_cache_get_failed", host=host, error=str(exc))

    text = await _download_robots(robots_url, timeout=timeout)
    if text is None:
        return None

    parser = _build_parser(robots_url, text, host=host)
    if parser is None:
        return None

    try:
        client = get_redis_operational()
        client.setex(cache_key, settings.SCRAPER_ROBOTS_CACHE_TTL, text)
        logger.debug("robots_cache_populated", host=host, ttl=settings.SCRAPER_ROBOTS_CACHE_TTL)
    except Exception as exc:
        logger.warning("robots_cache_set_failed", host=host, error=str(exc))

    return parser


async def is_allowed(
    url: str,
    user_agent: str = "marketsuite-scraper",
    *,
    timeout: float | None = None,
) -> bool:
    """ Retorna ``True`` quando o robots.txt autoriza ou quando fallback permite."""
    normalized_url, robots_url, host_key = _prepare_urls(url)
    timeout_value = timeout if timeout is not None else settings.SCRAPER_STEP_TIMEOUT_SECONDS
    parser = await _get_parser(host_key, robots_url, timeout=timeout_value)

    if parser is None:
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
        return False

    if not allowed:
        logger.info(
            "robots_disallowed",
            host=host_key,
            url=normalized_url,
            user_agent=user_agent,
        )

    return allowed


__all__ = ["is_allowed"]
