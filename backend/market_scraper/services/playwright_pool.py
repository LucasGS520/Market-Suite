""" Pool de contexts Playwright para aquisição de HTML com JavaScript (Camada 3).

O pool gerencia um único browser Chromium compartilhado e controla a
concorrência via ``asyncio.Semaphore``. Cada requisição obtém um contexto
isolado (sem cookies ou storage compartilhados entre chamadas), injetando
patches de stealth antes de navegar.

Uso típico (gerenciado pelo lifecycle da aplicação):

    # startup
    await playwright_pool.startup()

    # uso
    html = await playwright_pool.fetch_html("https://exemplo.com", timeout=30.0)

    # shutdown
    await playwright_pool.shutdown()

Variáveis de ambiente relevantes:
    PLAYWRIGHT_MAX_CONCURRENT   — máximo de contexts simultâneos (padrão: 5)
    PLAYWRIGHT_RECYCLE_AFTER    — requests por context antes de recriar (padrão: 50)
    PLAYWRIGHT_DISABLE_DEV_SHM  — passa --disable-dev-shm-usage ao Chromium (padrão: true)
    PLAYWRIGHT_DEBUG_SCREENSHOTS — salva screenshot em falhas (padrão: false)
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from shared.utils.logging_utils import sanitize_log_data

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright


logger = structlog.get_logger("playwright_pool")

# ─────────────────────────────────────────────────────────────────────────────
# Configuração via variáveis de ambiente
# ─────────────────────────────────────────────────────────────────────────────

_MAX_CONCURRENT: int = int(os.getenv("PLAYWRIGHT_MAX_CONCURRENT", "5"))
_RECYCLE_AFTER: int = int(os.getenv("PLAYWRIGHT_RECYCLE_AFTER", "50"))
_DISABLE_DEV_SHM: bool = os.getenv("PLAYWRIGHT_DISABLE_DEV_SHM", "true").lower() in {
    "1", "true", "on", "yes"
}
_DEBUG_SCREENSHOTS: bool = os.getenv("PLAYWRIGHT_DEBUG_SCREENSHOTS", "false").lower() in {
    "1", "true", "on", "yes"
}
_DEBUG_DIR = Path("tests/debug")

#Tipos de recurso bloqueados para reduzir uso de RAM (~40%)
_BLOCKED_RESOURCE_TYPES: frozenset[str] = frozenset({
    "image", "stylesheet", "font", "media", "other"
})

#User-Agent padrão Chrome pt-BR
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

#Script de stealth injetado em cada page — remove marcas de automação
_STEALTH_SCRIPT = """
(function () {
    // Remove navigator.webdriver (fingerprint mais crítico)
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true,
    });

    // Simula plugins de um Chrome real
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'Chrome PDF Plugin' },
            { name: 'Chrome PDF Viewer' },
            { name: 'Native Client' },
        ],
        configurable: true,
    });

    // Accept-Language pt-BR consistente com o header enviado
    Object.defineProperty(navigator, 'languages', {
        get: () => ['pt-BR', 'pt', 'en-US', 'en'],
        configurable: true,
    });

    // Objeto chrome presente em navegadores reais
    if (!window.chrome) {
        window.chrome = { runtime: {} };
    }

    // Remove indícios de Selenium/CDP
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
})();
"""


# ─────────────────────────────────────────────────────────────────────────────
# Exceções públicas
# ─────────────────────────────────────────────────────────────────────────────

class PlaywrightPoolNotReadyError(RuntimeError):
    """ Levantada quando ``fetch_html`` é chamado antes de ``startup()``."""

class PlaywrightTimeoutError(TimeoutError):
    """ Timeout durante navegação ou aguardo de conteúdo."""

    def __init__(self, *, url: str, timeout: float) -> None:
        super().__init__(f"Playwright timeout após {timeout}s em {url}")
        self.url = url
        self.timeout = timeout

class PlaywrightFetchError(Exception):
    """ Erro genérico de navegação (conexão recusada, crash de página, etc.)."""

    def __init__(self, *, url: str, reason: str) -> None:
        super().__init__(f"Playwright fetch error em {url}: {reason}")
        self.url = url
        self.reason = reason


# ─────────────────────────────────────────────────────────────────────────────
# Pool principal
# ─────────────────────────────────────────────────────────────────────────────

class PlaywrightPool:
    """ Gerencia um browser Chromium compartilhado com concorrência controlada.

    O pool limita contexts simultâneos via ``asyncio.Semaphore``. Cada chamada
    a ``fetch_html`` cria um contexto isolado, injeta stealth, bloqueia recursos
    pesados e fecha o contexto no ``finally`` para evitar vazamentos.
    """

    def __init__(self, *, max_concurrent: int = _MAX_CONCURRENT) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._max_concurrent = max_concurrent

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """ Inicializa o browser Chromium. Chamado no startup da aplicação."""
        from playwright.async_api import async_playwright

        args = [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
        ]
        if _DISABLE_DEV_SHM:
            args.append("--disable-dev-shm-usage")

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=args,
        )
        logger.info(
            "playwright_pool_started",
            max_concurrent=self._max_concurrent,
            disable_dev_shm=_DISABLE_DEV_SHM,
        )

    async def shutdown(self, *, grace_timeout: float = 10.0) -> None:
        """ Encerra o browser aguardando contexts pendentes (até ``grace_timeout`` s)."""
        logger.info("playwright_pool_shutdown_requested")

        if self._browser is not None:
            try:
                await asyncio.wait_for(self._browser.close(), timeout=grace_timeout)
            except asyncio.TimeoutError:
                logger.warning("playwright_pool_shutdown_timeout", grace_timeout=grace_timeout)
            finally:
                self._browser = None

        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.warning("playwright_stop_error", error=str(exc))
            finally:
                self._playwright = None

        logger.info("playwright_pool_stopped")

    @property
    def is_ready(self) -> bool:
        """ Retorna ``True`` quando o browser foi iniciado com sucesso."""
        return self._browser is not None

    # ── Fetch público ─────────────────────────────────────────────────────

    async def fetch_html(self, url: str, *, timeout: float = 30.0) -> str:
        """ Obtém HTML renderizado pelo Chromium com stealth e bloqueio de recursos.

        Args:
            url: URL alvo.
            timeout: Tempo máximo em segundos (padrão: 30s).

        Returns:
            HTML completo da página após ``domcontentloaded``.

        Raises:
            PlaywrightPoolNotReadyError: Pool não inicializado.
            PlaywrightTimeoutError: Navegação excedeu o timeout.
            PlaywrightFetchError: Erro de navegação ou página.
        """
        if self._browser is None:
            raise PlaywrightPoolNotReadyError(
                "PlaywrightPool não iniciado; chame startup() primeiro"
            )

        async with self._semaphore:
            return await self._fetch_in_context(url, timeout=timeout)

    # ── Internos ─────────────────────────────────────────────────────────

    async def _fetch_in_context(self, url: str, *, timeout: float) -> str:
        """ Cria contexto isolado, navega e retorna o HTML."""
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import TimeoutError as PlaywrightNativeTimeout

        context: BrowserContext = await self._browser.new_context(
            user_agent=_DEFAULT_USER_AGENT,
            locale="pt-BR",
            extra_http_headers={
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        try:
            page: Page = await context.new_page()

            #Stealth — remove fingerprints de automação
            stealth_ok = await self._inject_stealth(page)
            if not stealth_ok:
                logger.warning("playwright_stealth_injection_failed", url=sanitize_log_data(url))

            #Bloqueia recursos pesados para economizar RAM e latência
            await page.route("**/*", self._block_resources)

            timeout_ms = int(timeout * 1000)
            try:
                await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            except PlaywrightNativeTimeout as exc:
                await self._maybe_screenshot(page, url=url, reason="timeout")
                raise PlaywrightTimeoutError(url=url, timeout=timeout) from exc
            except PlaywrightError as exc:
                await self._maybe_screenshot(page, url=url, reason="navigation_error")
                raise PlaywrightFetchError(url=url, reason=str(exc)) from exc

            html = await page.content()
            logger.debug(
                "playwright_fetch_success",
                url=sanitize_log_data(url),
                html_size=len(html),
            )
            return html

        finally:
            await context.close()

    async def _inject_stealth(self, page: Page) -> bool:
        """ Injeta script de stealth na page. Retorna ``True`` se bem-sucedido."""
        try:
            await page.add_init_script(_STEALTH_SCRIPT)
            return True
        except Exception as exc:
            logger.debug("playwright_stealth_error", error=str(exc))
            return False

    async def _block_resources(self, route, request) -> None:
        """ Aborta requests de tipos de recurso pesados (imagens, CSS, fontes, mídia)."""
        if request.resource_type in _BLOCKED_RESOURCE_TYPES:
            await route.abort()
        else:
            await route.continue_()

    async def _maybe_screenshot(self, page: Page, *, url: str, reason: str) -> None:
        """ Salva screenshot de diagnóstico em ``tests/debug/`` quando habilitado."""
        if not _DEBUG_SCREENSHOTS:
            return
        try:
            _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            safe_name = url.replace("://", "_").replace("/", "_")[:80]
            path = _DEBUG_DIR / f"{reason}_{safe_name}.png"
            await page.screenshot(path=str(path))
            logger.debug("playwright_debug_screenshot_saved", path=str(path), reason=reason)
        except Exception as exc:
            logger.debug("playwright_screenshot_error", error=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Singleton global — gerenciado pelo lifecycle da aplicação
# ─────────────────────────────────────────────────────────────────────────────

playwright_pool = PlaywrightPool(max_concurrent=_MAX_CONCURRENT)


__all__ = [
    "PlaywrightPool",
    "PlaywrightPoolNotReadyError",
    "PlaywrightTimeoutError",
    "PlaywrightFetchError",
    "playwright_pool",
]
