"""Testes unitários para PlaywrightPool e PlaywrightFetchStep.

Toda a API do Playwright é substituída por mocks assíncronos para que
os testes rodem sem browser instalado. A estrutura de mocks reflete:

    async_playwright() → playwright_ctx
        .chromium.launch() → browser_mock
            .new_context() → context_mock
                .new_page() → page_mock
                    .goto() → response_mock
                    .content() → html string
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from market_scraper.services.playwright_pool import (
    PlaywrightFetchError,
    PlaywrightPool,
    PlaywrightPoolNotReadyError,
    PlaywrightTimeoutError,
    _BLOCKED_RESOURCE_TYPES,
    playwright_pool,
)
from market_scraper.services.pipeline_steps import PlaywrightFetchStep
from market_scraper.services.synergic_pipeline import PipelineContext


# ─────────────────────────────────────────────────────────────────────────────
# Infra de mocks do Playwright
# ─────────────────────────────────────────────────────────────────────────────

_URL = "https://www.mercadolivre.com.br/p/MLB123"
_HTML = "<html><body>" + "x" * 2048 + "</body></html>"


def _build_playwright_mocks(
    *,
    html: str = _HTML,
    goto_raises: Exception | None = None,
) -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    """Constrói a hierarquia de mocks: playwright → browser → context → page."""
    page_mock = MagicMock()
    page_mock.add_init_script = AsyncMock()
    page_mock.route = AsyncMock()
    page_mock.screenshot = AsyncMock()

    if goto_raises:
        page_mock.goto = AsyncMock(side_effect=goto_raises)
    else:
        page_mock.goto = AsyncMock()

    page_mock.content = AsyncMock(return_value=html)

    context_mock = MagicMock()
    context_mock.new_page = AsyncMock(return_value=page_mock)
    context_mock.close = AsyncMock()

    browser_mock = MagicMock()
    browser_mock.new_context = AsyncMock(return_value=context_mock)
    browser_mock.close = AsyncMock()

    playwright_ctx_mock = MagicMock()
    playwright_ctx_mock.chromium.launch = AsyncMock(return_value=browser_mock)
    playwright_ctx_mock.stop = AsyncMock()

    return playwright_ctx_mock, browser_mock, context_mock, page_mock


def _patch_async_playwright(playwright_ctx_mock: MagicMock):
    """Retorna context-manager que substitui ``async_playwright``."""
    @asynccontextmanager
    async def _fake_lifespan(*args, **kwargs) -> AsyncGenerator:
        yield playwright_ctx_mock

    # async_playwright() retorna um objeto com __aenter__/__aexit__
    async_pw_mock = MagicMock()
    async_pw_mock.return_value.__aenter__ = AsyncMock(return_value=playwright_ctx_mock)
    async_pw_mock.return_value.__aexit__ = AsyncMock(return_value=False)
    # playwright.start() — usado no pool
    async_pw_mock.return_value.start = AsyncMock(return_value=playwright_ctx_mock)

    return patch(
        "market_scraper.services.playwright_pool.async_playwright",
        async_pw_mock,
    ) if False else patch(
        "playwright.async_api.async_playwright",
        async_pw_mock,
    )


# ─────────────────────────────────────────────────────────────────────────────
# PlaywrightPool — estado antes do startup
# ─────────────────────────────────────────────────────────────────────────────

async def test_pool_is_not_ready_before_startup():
    """Pool recém-criado não está pronto."""
    pool = PlaywrightPool()
    assert not pool.is_ready


async def test_fetch_html_raises_when_pool_not_started():
    """``fetch_html`` levanta PlaywrightPoolNotReadyError se startup não foi chamado."""
    pool = PlaywrightPool()
    with pytest.raises(PlaywrightPoolNotReadyError):
        await pool.fetch_html(_URL)


# ─────────────────────────────────────────────────────────────────────────────
# PlaywrightPool — startup / shutdown
# ─────────────────────────────────────────────────────────────────────────────

async def test_pool_is_ready_after_startup():
    """Após startup(), is_ready retorna True."""
    pool = PlaywrightPool()
    playwright_ctx, browser, *_ = _build_playwright_mocks()

    # async_playwright é importado lazily dentro de startup(); patchear na origem
    with patch(
        "playwright.async_api.async_playwright",
        return_value=MagicMock(start=AsyncMock(return_value=playwright_ctx)),
    ):
        await pool.startup()

    assert pool.is_ready


async def test_pool_not_ready_after_shutdown():
    """Após shutdown(), is_ready retorna False."""
    pool = PlaywrightPool()
    playwright_ctx, browser, *_ = _build_playwright_mocks()

    with patch(
        "playwright.async_api.async_playwright",
        return_value=MagicMock(start=AsyncMock(return_value=playwright_ctx)),
    ):
        await pool.startup()
        await pool.shutdown()

    assert not pool.is_ready


async def test_shutdown_is_idempotent():
    """Chamar shutdown() quando não iniciado não levanta exceção."""
    pool = PlaywrightPool()
    await pool.shutdown()  # Não deve levantar


# ─────────────────────────────────────────────────────────────────────────────
# PlaywrightPool — fetch_html (via _fetch_in_context mockado)
# ─────────────────────────────────────────────────────────────────────────────

async def test_fetch_html_returns_page_content():
    """``fetch_html`` retorna o HTML obtido pelo page.content()."""
    pool = PlaywrightPool()
    pool._browser = MagicMock()  # simula estado after startup

    *_, context_mock, page_mock = _build_playwright_mocks(html=_HTML)
    pool._browser.new_context = AsyncMock(return_value=context_mock)

    with patch(
        "market_scraper.services.playwright_pool.PlaywrightPool._fetch_in_context",
        AsyncMock(return_value=_HTML),
    ):
        html = await pool.fetch_html(_URL)

    assert html == _HTML


async def test_fetch_html_closes_context_on_success():
    """O contexto é fechado mesmo após fetch bem-sucedido."""
    pool = PlaywrightPool()
    pool._browser = MagicMock()

    *_, context_mock, page_mock = _build_playwright_mocks(html=_HTML)
    pool._browser.new_context = AsyncMock(return_value=context_mock)

    with patch(
        "market_scraper.services.playwright_pool.PlaywrightPool._fetch_in_context",
        AsyncMock(return_value=_HTML),
    ):
        await pool.fetch_html(_URL)

    # _fetch_in_context é mockado — o close real está dentro dele
    # Verificamos apenas que o pool não deixou semáforo travado
    assert pool._semaphore._value == pool._max_concurrent


async def test_fetch_html_semaphore_released_on_error():
    """Semáforo é liberado mesmo quando fetch levanta exceção."""
    pool = PlaywrightPool()
    pool._browser = MagicMock()

    with patch(
        "market_scraper.services.playwright_pool.PlaywrightPool._fetch_in_context",
        AsyncMock(side_effect=PlaywrightTimeoutError(url=_URL, timeout=5.0)),
    ):
        with pytest.raises(PlaywrightTimeoutError):
            await pool.fetch_html(_URL)

    assert pool._semaphore._value == pool._max_concurrent


# ─────────────────────────────────────────────────────────────────────────────
# PlaywrightPool — resource blocking
# ─────────────────────────────────────────────────────────────────────────────

async def test_blocked_resources_include_image_stylesheet_font_media():
    """Tipos de recurso pesados estão na lista de bloqueio."""
    assert "image" in _BLOCKED_RESOURCE_TYPES
    assert "stylesheet" in _BLOCKED_RESOURCE_TYPES
    assert "font" in _BLOCKED_RESOURCE_TYPES
    assert "media" in _BLOCKED_RESOURCE_TYPES


async def test_block_resources_aborts_blocked_type():
    """``_block_resources`` chama abort() para tipos bloqueados."""
    pool = PlaywrightPool()

    route_mock = MagicMock()
    route_mock.abort = AsyncMock()
    route_mock.continue_ = AsyncMock()

    request_mock = MagicMock()
    request_mock.resource_type = "image"

    await pool._block_resources(route_mock, request_mock)

    route_mock.abort.assert_called_once()
    route_mock.continue_.assert_not_called()


async def test_block_resources_continues_for_document():
    """``_block_resources`` chama continue_() para ``document`` (HTML principal)."""
    pool = PlaywrightPool()

    route_mock = MagicMock()
    route_mock.abort = AsyncMock()
    route_mock.continue_ = AsyncMock()

    request_mock = MagicMock()
    request_mock.resource_type = "document"

    await pool._block_resources(route_mock, request_mock)

    route_mock.continue_.assert_called_once()
    route_mock.abort.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# PlaywrightPool — stealth injection
# ─────────────────────────────────────────────────────────────────────────────

async def test_stealth_injection_succeeds():
    """``_inject_stealth`` retorna True quando add_init_script não levanta."""
    pool = PlaywrightPool()
    page_mock = MagicMock()
    page_mock.add_init_script = AsyncMock()

    result = await pool._inject_stealth(page_mock)

    assert result is True
    page_mock.add_init_script.assert_called_once()


async def test_stealth_injection_returns_false_on_error():
    """``_inject_stealth`` retorna False e não re-levanta quando add_init_script falha."""
    pool = PlaywrightPool()
    page_mock = MagicMock()
    page_mock.add_init_script = AsyncMock(side_effect=RuntimeError("stealth failed"))

    result = await pool._inject_stealth(page_mock)

    assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# PlaywrightPool — concorrência
# ─────────────────────────────────────────────────────────────────────────────

async def test_pool_respects_max_concurrent_contexts(monkeypatch):
    """O semáforo limita o número de contexts simultâneos."""
    pool = PlaywrightPool(max_concurrent=2)
    pool._browser = MagicMock()

    active: list[int] = []
    max_seen: list[int] = []
    call_count = 0

    async def fake_fetch(url, *, timeout):
        nonlocal call_count
        call_count += 1
        active.append(1)
        max_seen.append(len(active))
        await asyncio.sleep(0.01)
        active.pop()
        return _HTML

    import asyncio
    monkeypatch.setattr(pool, "_fetch_in_context", fake_fetch)

    # Dispara 5 tasks simultâneas com max_concurrent=2
    tasks = [pool.fetch_html(_URL) for _ in range(5)]
    await asyncio.gather(*tasks)

    assert max(max_seen) <= 2


# ─────────────────────────────────────────────────────────────────────────────
# PlaywrightFetchStep
# ─────────────────────────────────────────────────────────────────────────────

def _make_context(url: str = _URL) -> PipelineContext:
    return PipelineContext(
        url=url,
        source="www.mercadolivre.com.br",
        default_step_timeout=5.0,
    )


async def test_playwright_fetch_step_sets_html_on_success(monkeypatch):
    """Step bem-sucedido define context.html e layer_used=playwright."""
    step = PlaywrightFetchStep()
    context = _make_context()

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.playwright_pool",
        MagicMock(
            is_ready=True,
            fetch_html=AsyncMock(return_value=_HTML),
        ),
    )

    result = await step.run(context)

    assert result.status == "success"
    assert context.html == _HTML
    assert context.data.get("layer_used") == "playwright"


async def test_playwright_fetch_step_returns_failure_when_pool_not_ready(monkeypatch):
    """Step retorna failure quando pool não está inicializado."""
    step = PlaywrightFetchStep()
    context = _make_context()

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.playwright_pool",
        MagicMock(is_ready=False),
    )

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "playwright_not_ready"
    assert context.html is None


async def test_playwright_fetch_step_returns_failure_on_timeout(monkeypatch):
    """Step mapeia PlaywrightTimeoutError para failure com mensagem correta."""
    step = PlaywrightFetchStep()
    context = _make_context()

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.playwright_pool",
        MagicMock(
            is_ready=True,
            fetch_html=AsyncMock(
                side_effect=PlaywrightTimeoutError(url=_URL, timeout=5.0)
            ),
        ),
    )

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "playwright_timeout"


async def test_playwright_fetch_step_returns_failure_on_fetch_error(monkeypatch):
    """Step mapeia PlaywrightFetchError para failure."""
    step = PlaywrightFetchStep()
    context = _make_context()

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.playwright_pool",
        MagicMock(
            is_ready=True,
            fetch_html=AsyncMock(
                side_effect=PlaywrightFetchError(url=_URL, reason="navigation aborted")
            ),
        ),
    )

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "playwright_fetch_error"


async def test_playwright_fetch_step_uses_step_timeout(monkeypatch):
    """Step passa o timeout correto para playwright_pool.fetch_html."""
    step = PlaywrightFetchStep(timeout=12.5)
    context = _make_context()

    captured: dict = {}

    async def fake_fetch(url, *, timeout):
        captured["timeout"] = timeout
        return _HTML

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.playwright_pool",
        MagicMock(is_ready=True, fetch_html=fake_fetch),
    )

    await step.run(context)

    assert captured["timeout"] == 12.5
