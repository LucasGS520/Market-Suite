"""Testes unitários adicionais para FetchHTMLStep.

Após a extração do FetchDecisionGate, FetchHTMLStep tem três
responsabilidades próprias:
  1. Early-return se HTML já está no contexto.
  2. Robots.txt check.
  3. Cache hit.
  4. Delegação ao FetchDecisionGate + mapeamento FetchResult → StepResult.

A lógica de cascata (rate limiter, curl_cffi, classifier, Playwright) é
responsabilidade de FetchDecisionGate e testada em test_fetch_decision_gate.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from market_scraper.services.fetch_decision_gate import FetchResult, FetchStatus
from market_scraper.services.pipeline_steps import FetchHTMLStep
from market_scraper.services.synergic_pipeline import PipelineContext


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_URL = "https://www.mercadolivre.com.br/p/MLB123"
_DOMAIN = "www.mercadolivre.com.br"
_HTML = "<html><body>" + "x" * 2048 + "</body></html>"


def _make_context(url: str = _URL) -> PipelineContext:
    return PipelineContext(url=url, source=_DOMAIN, default_step_timeout=5.0)


def _mock_gate(monkeypatch, return_value: FetchResult) -> AsyncMock:
    """Substitui fetch_decision_gate.fetch_with_fallback pelo FetchResult informado."""
    mock = AsyncMock(return_value=return_value)
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.fetch_decision_gate.fetch_with_fallback",
        mock,
    )
    return mock


def _robots_allow(monkeypatch) -> None:
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        AsyncMock(return_value=True),
    )


def _cache_miss(monkeypatch) -> None:
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.cache.get",
        MagicMock(return_value=None),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Early return
# ─────────────────────────────────────────────────────────────────────────────

async def test_fetch_html_step_skip_when_html_already_present(monkeypatch):
    """HTML já no contexto → retorno imediato sem chamar o gate."""
    step = FetchHTMLStep()
    context = _make_context()
    context.set_html(_HTML)

    gate_mock = AsyncMock()
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.fetch_decision_gate.fetch_with_fallback",
        gate_mock,
    )

    result = await step.run(context)

    assert result.status == "success"
    gate_mock.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Responsabilidades do próprio FetchHTMLStep (robots + cache)
# ─────────────────────────────────────────────────────────────────────────────

async def test_fetch_html_step_blocked_by_robots(monkeypatch):
    """Robots.txt não permite em modo block → failure sem chamar o gate."""
    step = FetchHTMLStep()
    context = _make_context()

    import market_scraper.services.pipeline_steps as _ps_module
    monkeypatch.setattr(_ps_module.settings, "SCRAPER_ROBOTS_MODE", "block")
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        AsyncMock(return_value=False),
    )

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "unsupported_by_robots"


async def test_fetch_html_step_returns_cached_html(monkeypatch):
    """Cache hit → retorna HTML sem chamar o gate."""
    step = FetchHTMLStep()
    context = _make_context()

    _robots_allow(monkeypatch)
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.cache.get",
        MagicMock(return_value=_HTML),
    )
    gate_mock = AsyncMock()
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.fetch_decision_gate.fetch_with_fallback",
        gate_mock,
    )

    result = await step.run(context)

    assert result.status == "success"
    assert result.message == "html_from_cache"
    assert context.html == _HTML
    gate_mock.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Mapeamento FetchResult → StepResult (gate mockado)
# ─────────────────────────────────────────────────────────────────────────────

async def test_fetch_html_step_maps_rate_limiter_cooldown(monkeypatch):
    """Gate retorna REJECT(rate_limiter_cooldown) → failure com mensagem correspondente."""
    step = FetchHTMLStep()
    context = _make_context()

    _robots_allow(monkeypatch)
    _cache_miss(monkeypatch)
    _mock_gate(monkeypatch, FetchResult(
        status=FetchStatus.REJECT,
        error_code="rate_limiter_cooldown",
    ))

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "rate_limiter_cooldown"


async def test_fetch_html_step_maps_layer1_success(monkeypatch):
    """Gate retorna SUCCESS via curl_cffi → HTML no contexto, layer_used=curl_cffi."""
    step = FetchHTMLStep()
    context = _make_context()

    _robots_allow(monkeypatch)
    _cache_miss(monkeypatch)
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.set", MagicMock())
    _mock_gate(monkeypatch, FetchResult(
        status=FetchStatus.SUCCESS,
        html=_HTML,
        layer_used="curl_cffi",
        fallback_taken=False,
        http_status=200,
        classification_reason="html_valid",
    ))

    result = await step.run(context)

    assert result.status == "success"
    assert result.message == "html_fetched_via_curl_cffi"
    assert context.html == _HTML
    assert context.data["layer_used"] == "curl_cffi"
    assert context.data["fallback_taken"] is False
    assert context.data["http_status"] == 200


async def test_fetch_html_step_maps_playwright_success(monkeypatch):
    """Gate retorna SUCCESS_AFTER_BROWSER → HTML no contexto com telemetria anti-bot."""
    step = FetchHTMLStep()
    context = _make_context()

    _robots_allow(monkeypatch)
    _cache_miss(monkeypatch)
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.set", MagicMock())
    _mock_gate(monkeypatch, FetchResult(
        status=FetchStatus.SUCCESS_AFTER_BROWSER,
        html=_HTML,
        layer_used="playwright",
        fallback_taken=True,
        anti_bot_detected=True,
        anti_bot_pattern="cloudflare_challenge",
        anti_bot_bypassed=True,
        http_status=200,
        classification_reason="anti_bot_page",
    ))

    result = await step.run(context)

    assert result.status == "success"
    assert result.message == "html_fetched_via_playwright"
    assert context.html == _HTML
    assert context.data["layer_used"] == "playwright"
    assert context.data["fallback_taken"] is True
    assert context.data["anti_bot_detected"] is True
    assert context.data["anti_bot_bypassed"] is True
    assert context.data["classification_reason"] == "anti_bot_page"


async def test_fetch_html_step_maps_product_unavailable(monkeypatch):
    """Gate retorna REJECT com availability=False → success com payload de disponibilidade."""
    step = FetchHTMLStep()
    context = _make_context()

    _robots_allow(monkeypatch)
    _cache_miss(monkeypatch)
    _mock_gate(monkeypatch, FetchResult(
        status=FetchStatus.REJECT,
        error_code="product_unavailable",
        http_status=404,
        availability=False,
        last_status="not_found",
    ))

    result = await step.run(context)

    assert result.status == "success"
    assert result.payload == {
        "name": None,
        "current_price": None,
        "url": _URL,
        "source": _DOMAIN,
        "availability": False,
        "last_status": "not_found",
    }
    assert context.html == ""
    assert context.data["http_status"] == 404
    assert context.data["availability"] is False
    assert context.data["last_status"] == "not_found"


async def test_fetch_html_step_maps_reject_too_many_redirects(monkeypatch):
    """Gate retorna REJECT(too_many_redirects) → failure com mensagem."""
    step = FetchHTMLStep()
    context = _make_context()

    _robots_allow(monkeypatch)
    _cache_miss(monkeypatch)
    _mock_gate(monkeypatch, FetchResult(
        status=FetchStatus.REJECT,
        error_code="too_many_redirects",
        http_status=422,
    ))

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "too_many_redirects"
    assert context.data["http_status"] == 422


async def test_fetch_html_step_maps_reject_not_found(monkeypatch):
    """Gate retorna REJECT(not_found) → failure com mensagem."""
    step = FetchHTMLStep()
    context = _make_context()

    _robots_allow(monkeypatch)
    _cache_miss(monkeypatch)
    _mock_gate(monkeypatch, FetchResult(
        status=FetchStatus.REJECT,
        error_code="not_found",
        classification_reason="not_found",
    ))

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "not_found"


async def test_fetch_html_step_maps_reject_after_playwright_timeout(monkeypatch):
    """Gate retorna REJECT_AFTER_BROWSER(playwright_timeout) → failure."""
    step = FetchHTMLStep()
    context = _make_context()

    _robots_allow(monkeypatch)
    _cache_miss(monkeypatch)
    _mock_gate(monkeypatch, FetchResult(
        status=FetchStatus.REJECT_AFTER_BROWSER,
        error_code="playwright_timeout",
    ))

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "playwright_timeout"


async def test_fetch_html_step_maps_reject_after_playwright_fetch_error(monkeypatch):
    """Gate retorna REJECT_AFTER_BROWSER(playwright_fetch_error) → failure."""
    step = FetchHTMLStep()
    context = _make_context()

    _robots_allow(monkeypatch)
    _cache_miss(monkeypatch)
    _mock_gate(monkeypatch, FetchResult(
        status=FetchStatus.REJECT_AFTER_BROWSER,
        error_code="playwright_fetch_error",
    ))

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "playwright_fetch_error"


async def test_fetch_html_step_maps_anti_bot_page_without_playwright(monkeypatch):
    """Gate retorna REJECT(anti_bot_page) (Playwright indisponível) → failure."""
    step = FetchHTMLStep()
    context = _make_context()

    _robots_allow(monkeypatch)
    _cache_miss(monkeypatch)
    _mock_gate(monkeypatch, FetchResult(
        status=FetchStatus.REJECT,
        error_code="anti_bot_page",
        anti_bot_detected=True,
        anti_bot_pattern="cloudflare_challenge",
    ))

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "anti_bot_page"
    assert context.data["anti_bot_detected"] is True


async def test_fetch_html_step_passes_budget_timeouts_to_gate(monkeypatch):
    """Gate recebe http_timeout e browser_timeout vindos dos orçamentos de configuração."""
    from market_scraper.core.config_scraper import settings

    step = FetchHTMLStep()
    context = _make_context()

    captured: dict = {}

    async def fake_fetch(url, *, domain, force_refresh, http_timeout, browser_timeout):
        captured["http_timeout"] = http_timeout
        captured["browser_timeout"] = browser_timeout
        return FetchResult(
            status=FetchStatus.SUCCESS,
            html=_HTML,
            layer_used="curl_cffi",
            http_status=200,
        )

    _robots_allow(monkeypatch)
    _cache_miss(monkeypatch)
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.set", MagicMock())
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.fetch_decision_gate.fetch_with_fallback",
        fake_fetch,
    )

    await step.run(context)

    assert captured["http_timeout"] == settings.SCRAPER_HTTP_BUDGET_SECONDS
    assert captured["browser_timeout"] == settings.SCRAPER_BROWSER_BUDGET_SECONDS
