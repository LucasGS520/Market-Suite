"""HttpCollector via HttpCrawler + CurlImpersonateHttpClient do Crawlee.

Coleta HTTP com fingerprint de browser real (curl_cffi).
Retries delegados ao HttpCrawler (max_request_retries).
Lifecycle gerenciado por CrawleeRuntime.startup()/shutdown().
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any
from uuid import uuid4

import structlog
from curl_cffi.requests.exceptions import RequestException as CurlRequestError
from crawlee.errors import ProxyError

from market_scraper.core.config_scraper import settings

logger = structlog.get_logger("http_collector")

_CURL_UNSUPPORTED_PROTO = 1
_CURL_URL_MALFORMAT = 3
_CURL_TOO_MANY_REDIRECTS = 47

_MAX_CONTENT_BYTES: int = settings.SCRAPER_HTTP_MAX_CONTENT_LENGTH


class HttpCollector:
    """Coleta HTTP via HttpCrawler com CurlImpersonateHttpClient.

    Retries delegados ao crawler (max_request_retries).
    Stateful — lifecycle gerenciado por CrawleeRuntime.startup()/shutdown().
    """

    def __init__(self, *, retries: int | None = None) -> None:
        self._retries = retries if retries is not None else settings.SCRAPER_HTTP_RETRIES
        self._crawler: Any = None
        self._pending: dict[str, asyncio.Future[tuple[str, int]]] = {}
        self._run_task: asyncio.Task[Any] | None = None

    @property
    def is_ready(self) -> bool:
        return (
            self._run_task is not None
            and not self._run_task.done()
            and self._crawler is not None
        )

    async def startup(self) -> None:
        from datetime import timedelta

        from crawlee.crawlers import HttpCrawler, HttpCrawlingContext
        from crawlee.http_clients import CurlImpersonateHttpClient
        from crawlee.proxy_configuration import ProxyConfiguration
        from crawlee.sessions import SessionPool
        from crawlee.storage_clients import MemoryStorageClient

        collector = self

        proxy_cfg: ProxyConfiguration | None = None
        if settings.SCRAPER_PROXY_URLS:
            proxy_urls = [u.strip() for u in settings.SCRAPER_PROXY_URLS.split("||") if u.strip()]
            if proxy_urls:
                proxy_cfg = ProxyConfiguration(proxy_urls=proxy_urls)

        session_pool = SessionPool(max_pool_size=settings.SCRAPER_SESSION_POOL_MAX_SIZE)

        self._crawler = HttpCrawler(
            http_client=CurlImpersonateHttpClient(
                max_redirects=settings.SCRAPER_HTTP_MAX_REDIRECTS,
            ),
            max_request_retries=self._retries,
            request_handler_timeout=timedelta(seconds=settings.SCRAPER_HTTP_BUDGET_SECONDS),
            storage_client=MemoryStorageClient(),
            configure_logging=False,
            keep_alive=True,
            proxy_configuration=proxy_cfg,
            session_pool=session_pool,
        )

        @self._crawler.router.default_handler
        async def _handler(context: HttpCrawlingContext) -> None:
            request_id: str = context.request.user_data.get("_request_id", "")
            session_id = context.session.id if context.session else "none"
            status = context.http_response.status_code

            #Aposentar sessão em bloqueio ou rate limit — impede reuso de identidade comprometida
            if status in (403, 429) and context.session:
                context.session.retire()
                logger.info(
                    "http_session_retired",
                    session_id=session_id,
                    reason=f"http_{status}",
                )

            future = collector._pending.get(request_id)
            if future and not future.done():
                body = await context.http_response.read()
                html = body[:_MAX_CONTENT_BYTES].decode("utf-8", errors="replace")
                future.set_result((html, status))
                logger.debug(
                    "http_collect",
                    request_id=request_id,
                    session_id=session_id,
                    url=context.request.url,
                    status=status,
                    html_size=len(html),
                )

        @self._crawler.failed_request_handler
        async def _failed(context: Any, error: Exception) -> None:
            request_id: str = context.request.user_data.get("_request_id", "")
            session_id = context.session.id if context.session else "none"

            #Aposentar sessão quando o proxy falhou — marca identidade como ruim
            if isinstance(error, ProxyError) and context.session:
                context.session.retire()
                logger.info(
                    "http_session_retired",
                    session_id=session_id,
                    reason="proxy_error",
                    error=type(error).__name__,
                )

            future = collector._pending.get(request_id)
            if future and not future.done():
                future.set_exception(error)
                logger.debug(
                    "http_collect_failed",
                    request_id=request_id,
                    session_id=session_id,
                    url=context.request.url,
                    error=type(error).__name__,
                )

        self._run_task = asyncio.create_task(self._crawler.run())
        await asyncio.sleep(0.1)
        logger.info(
            "http_collector_started",
            proxy_enabled=proxy_cfg is not None,
            session_pool_size=settings.SCRAPER_SESSION_POOL_MAX_SIZE,
        )

    async def shutdown(self) -> None:
        if self._crawler is not None:
            self._crawler.stop()
        if self._run_task is not None:
            with suppress(asyncio.CancelledError, asyncio.TimeoutError, Exception):
                await asyncio.wait_for(self._run_task, timeout=10.0)
        self._crawler = None
        self._run_task = None
        self._pending.clear()
        logger.info("http_collector_stopped")

    async def fetch(
        self,
        url: str,
        *,
        timeout: float,
        bound_logger: structlog.stdlib.BoundLogger | None = None,
    ) -> tuple[str | None, int | None, Exception | None, str | None]:
        """Enfileira URL no HttpCrawler e aguarda resultado via Future.

        Retorna (html, http_status, error, error_code).
        error_code não-None indica erro fatal que dispensa o classificador de política.
        """
        from crawlee import Request as CrawleeRequest

        log = bound_logger or logger

        if not self.is_ready:
            log.warning("http_collector_not_started", url=url)
            return None, None, RuntimeError("HttpCollector not started"), None

        request_id = str(uuid4())
        future: asyncio.Future[tuple[str, int]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        await self._crawler.add_requests([
            CrawleeRequest.from_url(
                url,
                unique_key=request_id,
                user_data={"_request_id": request_id},
            )
        ])

        try:
            html, status = await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
            return html, status, None, None
        except asyncio.TimeoutError as exc:
            return None, None, exc, None
        except CurlRequestError as exc:
            code = getattr(exc, "code", 0)
            if code == _CURL_TOO_MANY_REDIRECTS:
                return None, None, exc, "too_many_redirects"
            if code in (_CURL_UNSUPPORTED_PROTO, _CURL_URL_MALFORMAT):
                return None, None, exc, "invalid_url"
            return None, None, exc, None
        except ProxyError as exc:
            return None, None, exc, None
        except Exception as exc:
            return None, None, exc, None
        finally:
            self._pending.pop(request_id, None)


__all__ = ["HttpCollector"]
