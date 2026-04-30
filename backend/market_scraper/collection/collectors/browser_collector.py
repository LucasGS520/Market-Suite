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
import time
from contextlib import suppress
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from market_scraper.core.config_scraper import settings
from market_scraper.services.response_classifier import (
    count_product_signals,
    detect_anti_bot_pattern,
    has_product_signals,
)
from shared.utils.logging_utils import sanitize_log_data

logger = structlog.get_logger("browser_collector")

# ── Configuração ──────────────────────────────────────────────────────────────

_DISABLE_DEV_SHM: bool = os.getenv("PLAYWRIGHT_DISABLE_DEV_SHM", "true").lower() in {
    "1", "true", "on", "yes"
}
_DEBUG_SCREENSHOTS: bool = os.getenv("PLAYWRIGHT_DEBUG_SCREENSHOTS", "false").lower() in {
    "1", "true", "on", "yes"
}
_DEBUG_DIR = Path("tests/debug")

_BLOCKED_RESOURCE_TYPES: frozenset[str] = frozenset({
    "image", "stylesheet", "font", "media"
    # "other" removido: pode incluir XHR/Fetch com dados de produto úteis
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
        self._attempts: dict[str, int] = {}      # request_id → nº de tentativas de navegação
        self._nav_starts: dict[str, float] = {}  # request_id → time.monotonic() do início de nav
        self._seen_sessions: set[str] = set()    # session IDs já observados (para lifecycle log)

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
        from crawlee.proxy_configuration import ProxyConfiguration
        from crawlee.sessions import SessionPool
        from crawlee.storage_clients import MemoryStorageClient

        collector = self
        args = ["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        if _DISABLE_DEV_SHM:
            args.append("--disable-dev-shm-usage")

        proxy_cfg: ProxyConfiguration | None = None
        if settings.SCRAPER_PROXY_URLS:
            proxy_urls = [u.strip() for u in settings.SCRAPER_PROXY_URLS.split("||") if u.strip()]
            if proxy_urls:
                proxy_cfg = ProxyConfiguration(proxy_urls=proxy_urls)

        session_pool = SessionPool(max_pool_size=settings.SCRAPER_SESSION_POOL_MAX_SIZE)

        _nav_timeout = settings.SCRAPER_BROWSER_NAVIGATION_TIMEOUT_SECONDS
        self._crawler = PlaywrightCrawler(
            browser_type="chromium",
            headless=True,
            fingerprint_generator="default",
            browser_launch_options={"args": args},
            goto_options={"wait_until": "domcontentloaded"},  # "load"/"networkidle" bloqueavam em challenge pages
            request_handler_timeout=timedelta(seconds=_nav_timeout + 3),
            keep_alive=True,
            max_request_retries=settings.SCRAPER_BROWSER_MAX_RETRIES,
            concurrency_settings=ConcurrencySettings(
                min_concurrency=1,
                desired_concurrency=1,
                max_concurrency=settings.SCRAPER_BROWSER_CONCURRENCY,
            ),
            storage_client=MemoryStorageClient(),
            configure_logging=False,
            proxy_configuration=proxy_cfg,
            session_pool=session_pool,
        )

        @self._crawler.pre_navigation_hook
        async def _pre_nav(context: PlaywrightPreNavCrawlingContext) -> None:
            await context.page.route("**/*", collector._block_resources)

            # ── Telemetria de navegação (sempre, independente de early-exit) ──
            request_id: str = context.request.user_data.get("_request_id", "")
            session_id = context.session.id if context.session else "none"

            attempt = collector._attempts.get(request_id, 0) + 1
            collector._attempts[request_id] = attempt
            collector._nav_starts[request_id] = time.monotonic()

            if context.session:
                if session_id not in collector._seen_sessions:
                    collector._seen_sessions.add(session_id)
                    logger.info("browser_session_created", session_id=session_id)
                else:
                    logger.debug(
                        "browser_session_reused",
                        session_id=session_id,
                        request_id=request_id,
                        attempt=attempt,
                    )

            logger.debug(
                "browser_nav_start",
                request_id=request_id,
                session_id=session_id,
                url=sanitize_log_data(context.request.url),
                attempt=attempt,
            )

            if not settings.SCRAPER_BROWSER_EARLY_EXIT_ENABLED:
                return

            min_bytes: int = settings.SCRAPER_BROWSER_EARLY_EXIT_MIN_HTML_BYTES

            async def _try_early_exit() -> None:
                try:
                    #Aguardar pequeno delay para React/Vue renderizar componentes iniciais
                    await asyncio.sleep(0.3)
                    html = await context.page.content()
                except Exception as exc:
                    logger.debug("early_exit_get_content_failed", error=str(exc))
                    return

                future = collector._pending.get(request_id)
                if not future or future.done():
                    return

                html_size = len(html)

                #Caminho 1: 2+ sinais fortes de produto → early success (evita falso-positivo em challenge pages)
                signal_count = count_product_signals(html)
                if html_size >= min_bytes and signal_count >= 2:
                    logger.debug(
                        "browser_early_exit",
                        reason="product_signals_found",
                        url=sanitize_log_data(context.request.url),
                        html_size=html_size,
                        signal_count=signal_count,
                    )
                    future.set_result(html)
                    await _cancel_navigation(context)
                    return

                #Caminho 2: challenge anti-bot sem produto → fast-fail + aposentar sessão
                anti_bot = detect_anti_bot_pattern(html)
                if anti_bot:
                    session_id = context.session.id if context.session else "none"
                    if context.session and settings.SCRAPER_SESSION_POOL_ENABLED:
                        context.session.retire()
                        logger.info(
                            "browser_session_retired",
                            session_id=session_id,
                            reason="anti_bot_detected",
                            pattern=anti_bot,
                        )
                    logger.debug(
                        "browser_early_exit_anti_bot",
                        url=sanitize_log_data(context.request.url),
                        pattern=anti_bot,
                        html_size=html_size,
                        session_id=session_id,
                    )
                    if _DEBUG_SCREENSHOTS:
                        await collector._maybe_screenshot(
                            context.page,
                            url=context.request.url,
                            reason="anti_bot",
                        )
                    future.set_result(html)
                    await _cancel_navigation(context)
                    return

                #Se nenhuma condição de early-exit, deixa navegação continuar
                logger.debug(
                    "early_exit_not_triggered",
                    reason="html_too_small_and_no_signals",
                    html_size=html_size,
                    min_bytes=min_bytes,
                    url=sanitize_log_data(context.request.url),
                )

            context.page.once(
                "domcontentloaded",
                lambda: asyncio.create_task(_try_early_exit()),
            )

            async def _cancel_navigation(ctx: PlaywrightPreNavCrawlingContext) -> None:
                """ Tenta encerrar navegação Playwright gracefully após early-exit."""
                try:
                    if hasattr(ctx.page, "stop_loading"):
                        await ctx.page.stop_loading()
                    logger.debug("navigation_stopped", url=sanitize_log_data(ctx.request.url))
                except Exception as exc:
                    logger.debug("cancel_navigation_failed", error=str(exc))

        @self._crawler.router.default_handler
        async def _handler(context: PlaywrightCrawlingContext) -> None:
            request_id: str = context.request.user_data.get("_request_id", "")
            session_id = context.session.id if context.session else "none"
            status = context.response.status if context.response else 0

            was_pending = request_id in collector._pending
            if not was_pending:
                logger.warning(
                    "browser_handler_orphan",
                    request_id=request_id,
                    url=sanitize_log_data(context.request.url),
                    # Future já removido: handler chegou depois do timeout em fetch()
                )

            nav_duration_ms: float | None = None
            t_nav = collector._nav_starts.get(request_id)
            if t_nav is not None:
                nav_duration_ms = round((time.monotonic() - t_nav) * 1000, 1)

            if status in (403, 429) and context.session and settings.SCRAPER_SESSION_POOL_ENABLED:
                context.session.retire()
                logger.info(
                    "browser_session_retired",
                    session_id=session_id,
                    reason=f"http_{status}",
                )
            future = collector._pending.get(request_id)
            html = await context.page.content()
            logger.debug(
                "browser_fetch_success",
                request_id=request_id,
                url=sanitize_log_data(context.request.url),
                session_id=session_id,
                status=status,
                html_size=len(html),
                nav_duration_ms=nav_duration_ms,
                was_pending=was_pending,
            )
            if future and not future.done():
                future.set_result(html)

        @self._crawler.failed_request_handler
        async def _failed(context: Any, error: Exception) -> None:
            request_id: str = context.request.user_data.get("_request_id", "")
            session_id = context.session.id if context.session else "none"

            was_pending = request_id in collector._pending

            nav_duration_ms: float | None = None
            t_nav = collector._nav_starts.get(request_id)
            if t_nav is not None:
                nav_duration_ms = round((time.monotonic() - t_nav) * 1000, 1)

            is_timeout = isinstance(error, TimeoutError) or "timeout" in type(error).__name__.lower()
            if is_timeout and context.session and settings.SCRAPER_SESSION_POOL_ENABLED:
                context.session.retire()
                logger.info(
                    "browser_session_retired",
                    session_id=session_id,
                    reason="timeout",
                    error=type(error).__name__,
                )

            logger.debug(
                "browser_fetch_failed",
                request_id=request_id,
                session_id=session_id,
                error=type(error).__name__,
                nav_duration_ms=nav_duration_ms,
                was_pending=was_pending,
            )

            future = collector._pending.get(request_id)
            if future and not future.done():
                future.set_exception(error)

        self._run_task = asyncio.create_task(self._crawler.run())
        await asyncio.sleep(0.1)
        self._browser_ready = True
        logger.info(
            "browser_collector_started",
            max_concurrent=settings.SCRAPER_BROWSER_CONCURRENCY,
            proxy_enabled=proxy_cfg is not None,
            session_pool_size=settings.SCRAPER_SESSION_POOL_MAX_SIZE,
            session_retirement_enabled=settings.SCRAPER_SESSION_POOL_ENABLED,
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
        self._attempts.clear()
        self._nav_starts.clear()
        self._seen_sessions.clear()
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

        t0 = time.monotonic()
        request_id = str(uuid4())
        self._attempts[request_id] = 0
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        logger.debug(
            "browser_fetch_start",
            request_id=request_id,
            url=sanitize_log_data(url),
            timeout=timeout,
        )

        await self._crawler.add_requests([
            CrawleeRequest.from_url(
                url,
                unique_key=request_id,
                user_data={"_request_id": request_id},
            )
        ])

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise PlaywrightTimeoutError(url=url, timeout=timeout) from exc
        except Exception as exc:
            raise PlaywrightFetchError(url=url, reason=str(exc)) from exc
        finally:
            self._pending.pop(request_id, None)
            self._attempts.pop(request_id, None)
            self._nav_starts.pop(request_id, None)
            logger.debug(
                "browser_fetch_end",
                request_id=request_id,
                url=sanitize_log_data(url),
                duration_ms=round((time.monotonic() - t0) * 1000, 1),
            )

    # ── Helpers internos ──────────────────────────────────────────────────────

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
