"""BrowserCollector via Crawlee PlaywrightCrawler persistente.

Fallback de browser para coleta de HTML renderizado. O lifecycle de browser,
contextos e páginas fica delegado ao Crawlee via PlaywrightCrawler com
keep_alive=True; este módulo mantém a porta pública usada pelo CrawleeRuntime.

Cada fetch() enfileira a URL com um request_id único e aguarda o resultado via
asyncio.Future. Concorrência controlada por ConcurrencySettings do Crawlee.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from shared.utils.logging_utils import sanitize_log_data

logger = structlog.get_logger("browser_collector")

# ── Configuração ──────────────────────────────────────────────────────────────

_MAX_CONCURRENT: int = int(os.getenv("PLAYWRIGHT_MAX_CONCURRENT", "5"))
_DISABLE_DEV_SHM: bool = os.getenv("PLAYWRIGHT_DISABLE_DEV_SHM", "true").lower() in {
    "1", "true", "on", "yes"
}
_DEBUG_SCREENSHOTS: bool = os.getenv("PLAYWRIGHT_DEBUG_SCREENSHOTS", "false").lower() in {
    "1", "true", "on", "yes"
}
_DEBUG_DIR = Path("tests/debug")

_BLOCKED_RESOURCE_TYPES: frozenset[str] = frozenset({
    "image", "stylesheet", "font", "media", "other"
})


# ── Exceções públicas ─────────────────────────────────────────────────────────

class PlaywrightPoolNotReadyError(RuntimeError):
    """Browser fallback não inicializado; startup() não foi chamado ou falhou."""


class PlaywrightTimeoutError(TimeoutError):
    """Timeout durante navegação via PlaywrightCrawler."""

    def __init__(self, *, url: str, timeout: float) -> None:
        super().__init__(f"Playwright timeout após {timeout}s em {url}")
        self.url = url
        self.timeout = timeout


class PlaywrightFetchError(Exception):
    """Erro genérico de navegação ou coleta via PlaywrightCrawler."""

    def __init__(self, *, url: str, reason: str) -> None:
        super().__init__(f"Playwright fetch error em {url}: {reason}")
        self.url = url
        self.reason = reason


# ── BrowserCollector ──────────────────────────────────────────────────────────

class PlaywrightBrowserCollector:
    """BrowserCollector delegando lifecycle ao Crawlee PlaywrightCrawler.

    Um único PlaywrightCrawler corre como tarefa de fundo (keep_alive=True).
    Cada fetch() enfileira a URL com request_id único e aguarda o resultado
    via asyncio.Future. Crawlee gerencia browser pool, contextos e páginas;
    este módulo mantém apenas as regras de produto: stealth, resource blocking.
    """

    def __init__(self) -> None:
        self._crawler: Any = None
        self._pending: dict[str, asyncio.Future[str]] = {}
        self._run_task: asyncio.Task[Any] | None = None
        self._browser_ready: bool = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Inicializa PlaywrightCrawler persistente como tarefa de fundo."""
        from crawlee import ConcurrencySettings
        from crawlee._request import Request as CrawleeRequest  # noqa: F401 (usado em fetch)
        from crawlee.crawlers import (
            PlaywrightCrawler,
            PlaywrightCrawlingContext,
            PlaywrightPreNavCrawlingContext,
        )
        from crawlee.storage_clients import MemoryStorageClient

        collector = self
        args = ["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        if _DISABLE_DEV_SHM:
            args.append("--disable-dev-shm-usage")

        self._crawler = PlaywrightCrawler(
            browser_type="chromium",
            headless=True,
            fingerprint_generator="default",
            browser_launch_options={"args": args},
            goto_options={"wait_until": "domcontentloaded"},
            keep_alive=True,
            max_request_retries=0,
            concurrency_settings=ConcurrencySettings(
                min_concurrency=1,
                desired_concurrency=1,
                max_concurrency=_MAX_CONCURRENT,
            ),
            storage_client=MemoryStorageClient(),
            configure_logging=False,
        )

        @self._crawler.pre_navigation_hook
        async def _pre_nav(context: PlaywrightPreNavCrawlingContext) -> None:
            await context.page.route("**/*", collector._block_resources)

        @self._crawler.router.default_handler
        async def _handler(context: PlaywrightCrawlingContext) -> None:
            request_id: str = context.request.user_data.get("_request_id", "")
            future = collector._pending.get(request_id)
            html = await context.page.content()
            logger.debug(
                "browser_fetch_success",
                url=sanitize_log_data(context.request.url),
                html_size=len(html),
            )
            if future and not future.done():
                future.set_result(html)

        @self._crawler.failed_request_handler
        async def _failed(context: Any, error: Exception) -> None:
            request_id: str = context.request.user_data.get("_request_id", "")
            future = collector._pending.get(request_id)
            if future and not future.done():
                future.set_exception(error)

        self._run_task = asyncio.create_task(self._crawler.run())
        try:
            await self._do_startup_warmup()
            self._browser_ready = True
            logger.info("browser_collector_started", max_concurrent=_MAX_CONCURRENT)
        except Exception as exc:
            logger.warning(
                "browser_collector_degraded",
                reason="warmup_failed",
                error=str(exc),
            )

    async def shutdown(self) -> None:
        """Para o PlaywrightCrawler persistente e aguarda encerramento."""
        if self._crawler is not None:
            self._crawler.stop()
        if self._run_task is not None:
            with suppress(asyncio.CancelledError, asyncio.TimeoutError, Exception):
                await asyncio.wait_for(self._run_task, timeout=10.0)
        self._crawler = None
        self._run_task = None
        self._browser_ready = False
        self._pending.clear()
        logger.info("browser_collector_stopped")

    @property
    def is_ready(self) -> bool:
        """True quando o PlaywrightCrawler está rodando e o browser pool está pronto."""
        return (
            self._run_task is not None
            and not self._run_task.done()
            and self._crawler is not None
            and self._browser_ready
        )

    # ── Fetch público ─────────────────────────────────────────────────────────

    async def fetch(
        self,
        url: str,
        *,
        timeout: float,
        domain: str | None = None,
    ) -> str:
        """Obtém HTML renderizado via PlaywrightCrawler.

        Args:
            url: URL alvo.
            timeout: Tempo máximo em segundos.
            domain: Reservado para compatibilidade de interface; não utilizado.

        Raises:
            PlaywrightPoolNotReadyError: Crawler não inicializado.
            PlaywrightTimeoutError: Timeout aguardando resultado.
            PlaywrightFetchError: Erro de navegação ou coleta.
        """
        _ = domain
        if not self.is_ready:
            raise PlaywrightPoolNotReadyError(
                "PlaywrightCrawler não iniciado; chame startup() primeiro"
            )

        from crawlee._request import Request as CrawleeRequest

        request_id = str(uuid4())
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        await self._crawler.add_requests([
            CrawleeRequest.from_url(
                url,
                unique_key=request_id,
                user_data={"_request_id": request_id},
            )
        ])

        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise PlaywrightTimeoutError(url=url, timeout=timeout) from exc
        except Exception as exc:
            raise PlaywrightFetchError(url=url, reason=str(exc)) from exc
        finally:
            self._pending.pop(request_id, None)

    # ── Helpers internos ──────────────────────────────────────────────────────

    async def _do_startup_warmup(self) -> None:
        """Enfileira requisição para about:blank e aguarda resultado.

        Confirma que o browser pool foi inicializado com sucesso antes de
        declarar o collector como pronto. Levanta exceção se o pool falhou.
        """
        from crawlee._request import Request as CrawleeRequest

        request_id = f"warmup-{uuid4()}"
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        await self._crawler.add_requests([
            CrawleeRequest.from_url(
                "about:blank",
                unique_key=request_id,
                user_data={"_request_id": request_id},
            )
        ])

        try:
            await asyncio.wait_for(asyncio.shield(future), timeout=30.0)
        except asyncio.TimeoutError as exc:
            raise TimeoutError("browser warmup timed out after 30s") from exc
        finally:
            self._pending.pop(request_id, None)

    async def _block_resources(self, route: Any, request: Any) -> None:
        if request.resource_type in _BLOCKED_RESOURCE_TYPES:
            await route.abort()
        else:
            await route.continue_()

    async def _maybe_screenshot(self, page: Any, *, url: str, reason: str) -> None:
        if not _DEBUG_SCREENSHOTS:
            return
        try:
            _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            safe_name = url.replace("://", "_").replace("/", "_")[:80]
            path = _DEBUG_DIR / f"{reason}_{safe_name}.png"
            await page.screenshot(path=str(path))
            logger.debug("browser_debug_screenshot_saved", path=str(path), reason=reason)
        except Exception as exc:
            logger.debug("browser_screenshot_error", error=str(exc))


__all__ = [
    "PlaywrightBrowserCollector",
    "PlaywrightFetchError",
    "PlaywrightPoolNotReadyError",
    "PlaywrightTimeoutError",
]
