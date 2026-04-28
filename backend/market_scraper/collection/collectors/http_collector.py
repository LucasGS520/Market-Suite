"""HttpCollector via CurlImpersonateHttpClient + SessionPool do Crawlee.

Camada de requisição HTTP leve com fingerprint de browser real (curl_cffi).
Lifecycle gerenciado por CrawleeRuntime.startup()/shutdown().
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import structlog
from curl_cffi.requests.exceptions import RequestException as CurlRequestError
from crawlee.errors import ProxyError
from crawlee.http_clients import CurlImpersonateHttpClient
from crawlee.sessions import SessionPool

from market_scraper.core.config_scraper import settings

logger = structlog.get_logger("http_collector")

_CURL_UNSUPPORTED_PROTO = 1
_CURL_URL_MALFORMAT = 3
_CURL_TOO_MANY_REDIRECTS = 47

_MAX_CONTENT_BYTES: int = settings.SCRAPER_HTTP_MAX_CONTENT_LENGTH


class HttpCollector:
    """Coleta HTTP via CurlImpersonateHttpClient + SessionPool do Crawlee.

    Stateful — lifecycle gerenciado por CrawleeRuntime.startup()/shutdown().
    """

    def __init__(
        self,
        *,
        http_client: CurlImpersonateHttpClient | None = None,
        session_pool: SessionPool | None = None,
        retries: int | None = None,
    ) -> None:
        self._http_client = http_client
        self._session_pool = session_pool
        self._retries = retries if retries is not None else settings.SCRAPER_HTTP_RETRIES
        self._owns_resources = http_client is None

    @property
    def is_ready(self) -> bool:
        return self._http_client is not None and self._session_pool is not None

    async def startup(self) -> None:
        if self._owns_resources:
            client = CurlImpersonateHttpClient()
            await client.__aenter__()
            pool = SessionPool(max_pool_size=100)
            await pool.__aenter__()
            self._http_client = client
            self._session_pool = pool
            logger.info("http_collector_started")

    async def shutdown(self) -> None:
        if self._owns_resources:
            if self._http_client:
                await self._http_client.__aexit__(None, None, None)
                self._http_client = None
            if self._session_pool:
                await self._session_pool.__aexit__(None, None, None)
                self._session_pool = None
            logger.info("http_collector_stopped")

    async def fetch(
        self,
        url: str,
        *,
        timeout: float,
        bound_logger: structlog.stdlib.BoundLogger | None = None,
    ) -> tuple[str | None, int | None, Exception | None, str | None]:
        """Executa requisição HTTP com impersonation e retry via SessionPool.

        Retorna (html, http_status, error, error_code).
        error_code não-None indica erro fatal que dispensa o classificador de política.
        """
        log = bound_logger or logger

        if not self.is_ready:
            log.warning("http_collector_not_started", url=url)
            return None, None, RuntimeError("HttpCollector not started"), None

        last_error: Exception | None = None

        for attempt_n in range(self._retries + 1):
            session = await self._session_pool.get_session()

            try:
                response = await self._http_client.send_request(
                    url,
                    session=session,
                    timeout=timedelta(seconds=timeout),
                )
                content = response.read()[:_MAX_CONTENT_BYTES]
                html = content.decode("utf-8", errors="replace")
                session.mark_good()
                return html, response.status_code, None, None

            except asyncio.TimeoutError as exc:
                session.mark_bad()
                return None, None, exc, None

            except CurlRequestError as exc:
                code = getattr(exc, "code", 0)
                if code == _CURL_TOO_MANY_REDIRECTS:
                    session.mark_bad()
                    return None, None, exc, "too_many_redirects"
                if code in (_CURL_UNSUPPORTED_PROTO, _CURL_URL_MALFORMAT):
                    return None, None, exc, "invalid_url"
                session.mark_bad()
                last_error = exc
                if attempt_n < self._retries:
                    log.warning(
                        "http_attempt_retrying",
                        url=url,
                        attempt=attempt_n + 1,
                        error=str(exc),
                    )
                    continue

            except ProxyError as exc:
                session.mark_bad()
                return None, None, exc, None

        return None, None, last_error, None


__all__ = ["HttpCollector"]
