"""Testes unitários para CascadeFetchStep.

Verifica o fluxo completo de aquisição em cascata:
  - Rate limiter pré/pós-requisição
  - HTML já presente no contexto (early return)
  - Robots.txt bloqueado
  - Cache hit
  - Camada 1 (curl_cffi) com sucesso → sem escalamento
  - Camada 1 com resposta classificada como SCALE → escalamento Playwright
  - Erros HTTP (429, 403, 404) com mapeamento correto
  - Playwright indisponível após SCALE
  - Playwright com timeout / erro
  - Fallback correto de metadados no context.data
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from market_scraper.services.pipeline_steps import CascadeFetchStep
from market_scraper.services.response_classifier import (
    ClassificationAction,
    ClassificationResult,
)
from market_scraper.services.playwright_pool import (
    PlaywrightFetchError,
    PlaywrightPoolNotReadyError,
    PlaywrightTimeoutError,
)
from market_scraper.services.synergic_pipeline import PipelineContext


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_URL = "https://www.mercadolivre.com.br/p/MLB123"
_DOMAIN = "www.mercadolivre.com.br"
_HTML = "<html><body>" + "x" * 2048 + "</body></html>"


def _make_context(url: str = _URL) -> PipelineContext:
    return PipelineContext(
        url=url,
        source=_DOMAIN,
        default_step_timeout=5.0,
    )


def _classify_success() -> ClassificationResult:
    return ClassificationResult(
        action=ClassificationAction.SUCCESS,
        next_layer=None,
        reason="html_ok",
    )


def _classify_scale(reason: str = "anti_bot_page") -> ClassificationResult:
    return ClassificationResult(
        action=ClassificationAction.SCALE,
        next_layer=3,
        reason=reason,
    )


def _classify_reject(reason: str = "not_found") -> ClassificationResult:
    return ClassificationResult(
        action=ClassificationAction.REJECT,
        next_layer=None,
        reason=reason,
    )


def _fake_rate_limiter(*, allowed: bool = True, layer: int = 1) -> MagicMock:
    rl = MagicMock()
    rl.should_allow = AsyncMock(return_value=(allowed, layer))
    rl.update_history = AsyncMock()
    return rl


def _fake_playwright_pool(*, ready: bool = True, html: str = _HTML) -> MagicMock:
    pool = MagicMock()
    pool.is_ready = ready
    pool.fetch_html = AsyncMock(return_value=html)
    return pool


# ─────────────────────────────────────────────────────────────────────────────
# Early-return e pré-condições
# ─────────────────────────────────────────────────────────────────────────────

async def test_cascade_skip_when_html_already_present(monkeypatch):
    """HTML já disponível no contexto → retorno imediato sem download."""
    step = CascadeFetchStep()
    context = _make_context()
    context.set_html(_HTML)

    rl = _fake_rate_limiter()
    monkeypatch.setattr("market_scraper.services.pipeline_steps.adaptive_rate_limiter", rl)

    result = await step.run(context)

    assert result.status == "success"
    rl.should_allow.assert_not_called()


async def test_cascade_blocked_by_rate_limiter(monkeypatch):
    """Rate limiter retorna allowed=False → failure com cooldown."""
    step = CascadeFetchStep()
    context = _make_context()

    rl = _fake_rate_limiter(allowed=False, layer=0)
    monkeypatch.setattr("market_scraper.services.pipeline_steps.adaptive_rate_limiter", rl)

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "rate_limiter_cooldown"
    assert context.html is None


async def test_cascade_blocked_by_robots(monkeypatch):
    """Robots.txt não permite → failure sem download."""
    step = CascadeFetchStep()
    context = _make_context()

    monkeypatch.setattr("market_scraper.services.pipeline_steps.adaptive_rate_limiter", _fake_rate_limiter())
    monkeypatch.setattr("market_scraper.services.pipeline_steps.robots.is_allowed", AsyncMock(return_value=False))

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "unsupported_by_robots"


async def test_cascade_returns_cached_html(monkeypatch):
    """Cache hit → retorna HTML sem download e sem escalonamento."""
    step = CascadeFetchStep()
    context = _make_context()

    monkeypatch.setattr("market_scraper.services.pipeline_steps.adaptive_rate_limiter", _fake_rate_limiter())
    monkeypatch.setattr("market_scraper.services.pipeline_steps.robots.is_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.get", MagicMock(return_value=_HTML))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.set", MagicMock())

    # cache é usado quando should_use_cache retorna True (force_refresh=False)
    result = await step.run(context)

    assert result.status == "success"
    assert result.message == "html_from_cache"
    assert context.html == _HTML


# ─────────────────────────────────────────────────────────────────────────────
# Camada 1 — curl_cffi
# ─────────────────────────────────────────────────────────────────────────────

async def test_cascade_layer1_success(monkeypatch):
    """Camada 1 sucesso + classifier SUCCESS → sem Playwright, layer_used='curl_cffi'."""
    step = CascadeFetchStep()
    context = _make_context()

    rl = _fake_rate_limiter()
    monkeypatch.setattr("market_scraper.services.pipeline_steps.adaptive_rate_limiter", rl)
    monkeypatch.setattr("market_scraper.services.pipeline_steps.robots.is_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.get", MagicMock(return_value=None))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.set", MagicMock())
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.singleflight.coalesce_with_leader",
        AsyncMock(return_value=(_HTML, True)),
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps._response_classifier.classify",
        MagicMock(return_value=_classify_success()),
    )

    result = await step.run(context)

    assert result.status == "success"
    assert result.message == "html_fetched_via_curl_cffi"
    assert context.html == _HTML
    assert context.data["layer_used"] == "curl_cffi"
    assert context.data["fallback_taken"] is False
    rl.update_history.assert_awaited_once_with(_DOMAIN, success=True, layer_used=1)


async def test_cascade_layer1_success_coalesced(monkeypatch):
    """Singleflight coalescido (is_leader=False) → ainda retorna o HTML corretamente."""
    step = CascadeFetchStep()
    context = _make_context()

    monkeypatch.setattr("market_scraper.services.pipeline_steps.adaptive_rate_limiter", _fake_rate_limiter())
    monkeypatch.setattr("market_scraper.services.pipeline_steps.robots.is_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.get", MagicMock(return_value=None))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.set", MagicMock())
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.singleflight.coalesce_with_leader",
        AsyncMock(return_value=(_HTML, False)),  # is_leader=False → coalesced
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps._response_classifier.classify",
        MagicMock(return_value=_classify_success()),
    )

    result = await step.run(context)

    assert result.status == "success"
    assert context.html == _HTML


# ─────────────────────────────────────────────────────────────────────────────
# Erros HTTP na Camada 1
# ─────────────────────────────────────────────────────────────────────────────

async def test_cascade_layer1_too_many_redirects(monkeypatch):
    """TooManyRedirects → failure, http_status=422, history atualizado."""
    step = CascadeFetchStep()
    context = _make_context()

    rl = _fake_rate_limiter()
    monkeypatch.setattr("market_scraper.services.pipeline_steps.adaptive_rate_limiter", rl)
    monkeypatch.setattr("market_scraper.services.pipeline_steps.robots.is_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.get", MagicMock(return_value=None))
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.singleflight.coalesce_with_leader",
        AsyncMock(side_effect=httpx.TooManyRedirects("too many")),
    )

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "too_many_redirects"
    assert context.data["http_status"] == 422
    rl.update_history.assert_awaited_once()


async def test_cascade_layer1_invalid_url(monkeypatch):
    """InvalidURL → failure, http_status=422."""
    step = CascadeFetchStep()
    context = _make_context()

    rl = _fake_rate_limiter()
    monkeypatch.setattr("market_scraper.services.pipeline_steps.adaptive_rate_limiter", rl)
    monkeypatch.setattr("market_scraper.services.pipeline_steps.robots.is_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.get", MagicMock(return_value=None))
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.singleflight.coalesce_with_leader",
        AsyncMock(side_effect=httpx.InvalidURL("bad url")),
    )

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "invalid_url"


async def test_cascade_layer1_404_infers_unavailability(monkeypatch):
    """HTTPStatusError 404 → infer_availability retorna indisponível → success com availability=False."""
    step = CascadeFetchStep()
    context = _make_context()

    fake_req = httpx.Request("GET", _URL)
    fake_resp = httpx.Response(404, request=fake_req)
    exc_404 = httpx.HTTPStatusError("HTTP 404", request=fake_req, response=fake_resp)

    rl = _fake_rate_limiter()
    monkeypatch.setattr("market_scraper.services.pipeline_steps.adaptive_rate_limiter", rl)
    monkeypatch.setattr("market_scraper.services.pipeline_steps.robots.is_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.get", MagicMock(return_value=None))
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.singleflight.coalesce_with_leader",
        AsyncMock(side_effect=exc_404),
    )

    result = await step.run(context)

    assert result.status == "success"
    assert context.data["http_status"] == 404
    assert context.data.get("availability") is False
    rl.update_history.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# Classificador → SCALE → Playwright (Camada 3)
# ─────────────────────────────────────────────────────────────────────────────

async def test_cascade_scales_to_playwright_on_anti_bot(monkeypatch):
    """Classifier retorna SCALE (anti_bot) → Playwright obtém HTML."""
    step = CascadeFetchStep()
    context = _make_context()

    rl = _fake_rate_limiter()
    pw = _fake_playwright_pool(ready=True, html=_HTML)

    monkeypatch.setattr("market_scraper.services.pipeline_steps.adaptive_rate_limiter", rl)
    monkeypatch.setattr("market_scraper.services.pipeline_steps.robots.is_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.get", MagicMock(return_value=None))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.set", MagicMock())
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.singleflight.coalesce_with_leader",
        AsyncMock(return_value=(_HTML, True)),
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps._response_classifier.classify",
        MagicMock(return_value=_classify_scale("anti_bot_page")),
    )
    monkeypatch.setattr("market_scraper.services.pipeline_steps.playwright_pool", pw)

    result = await step.run(context)

    assert result.status == "success"
    assert result.message == "html_fetched_via_playwright"
    assert context.html == _HTML
    assert context.data["layer_used"] == "playwright"
    assert context.data["fallback_taken"] is True
    assert context.data["classification_reason"] == "anti_bot_page"
    # update_history chamado 2 vezes: L1 fail + L3 success
    assert rl.update_history.await_count == 2


async def test_cascade_playwright_not_ready_after_scale(monkeypatch):
    """SCALE mas Playwright não inicializado → failure playwright_not_ready."""
    step = CascadeFetchStep()
    context = _make_context()

    monkeypatch.setattr("market_scraper.services.pipeline_steps.adaptive_rate_limiter", _fake_rate_limiter())
    monkeypatch.setattr("market_scraper.services.pipeline_steps.robots.is_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.get", MagicMock(return_value=None))
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.singleflight.coalesce_with_leader",
        AsyncMock(return_value=(_HTML, True)),
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps._response_classifier.classify",
        MagicMock(return_value=_classify_scale()),
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.playwright_pool",
        _fake_playwright_pool(ready=False),
    )

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "playwright_not_ready"


async def test_cascade_playwright_timeout_after_scale(monkeypatch):
    """Playwright levanta PlaywrightTimeoutError → failure playwright_timeout."""
    step = CascadeFetchStep()
    context = _make_context()

    pw = MagicMock()
    pw.is_ready = True
    pw.fetch_html = AsyncMock(side_effect=PlaywrightTimeoutError(url=_URL, timeout=5.0))

    monkeypatch.setattr("market_scraper.services.pipeline_steps.adaptive_rate_limiter", _fake_rate_limiter())
    monkeypatch.setattr("market_scraper.services.pipeline_steps.robots.is_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.get", MagicMock(return_value=None))
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.singleflight.coalesce_with_leader",
        AsyncMock(return_value=(_HTML, True)),
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps._response_classifier.classify",
        MagicMock(return_value=_classify_scale()),
    )
    monkeypatch.setattr("market_scraper.services.pipeline_steps.playwright_pool", pw)

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "playwright_timeout"


async def test_cascade_playwright_fetch_error_after_scale(monkeypatch):
    """Playwright levanta PlaywrightFetchError → failure playwright_fetch_error."""
    step = CascadeFetchStep()
    context = _make_context()

    pw = MagicMock()
    pw.is_ready = True
    pw.fetch_html = AsyncMock(
        side_effect=PlaywrightFetchError(url=_URL, reason="navigation aborted")
    )

    monkeypatch.setattr("market_scraper.services.pipeline_steps.adaptive_rate_limiter", _fake_rate_limiter())
    monkeypatch.setattr("market_scraper.services.pipeline_steps.robots.is_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.get", MagicMock(return_value=None))
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.singleflight.coalesce_with_leader",
        AsyncMock(return_value=(_HTML, True)),
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps._response_classifier.classify",
        MagicMock(return_value=_classify_scale()),
    )
    monkeypatch.setattr("market_scraper.services.pipeline_steps.playwright_pool", pw)

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "playwright_fetch_error"


# ─────────────────────────────────────────────────────────────────────────────
# Classificador → REJECT
# ─────────────────────────────────────────────────────────────────────────────

async def test_cascade_classifier_reject_returns_failure(monkeypatch):
    """Classifier REJECT sem exceção → failure com reason como mensagem."""
    step = CascadeFetchStep()
    context = _make_context()

    rl = _fake_rate_limiter()
    monkeypatch.setattr("market_scraper.services.pipeline_steps.adaptive_rate_limiter", rl)
    monkeypatch.setattr("market_scraper.services.pipeline_steps.robots.is_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.get", MagicMock(return_value=None))
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.singleflight.coalesce_with_leader",
        AsyncMock(return_value=(None, True)),
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps._response_classifier.classify",
        MagicMock(return_value=_classify_reject("not_found")),
    )

    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "not_found"
    rl.update_history.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# Timeout customizado
# ─────────────────────────────────────────────────────────────────────────────

async def test_cascade_uses_step_timeout(monkeypatch):
    """Timeout do step é passado para download_html via singleflight."""
    step = CascadeFetchStep(timeout=12.5)
    context = _make_context()

    captured: dict = {}

    async def fake_download(url, *, timeout):
        captured["timeout"] = timeout
        return _HTML

    monkeypatch.setattr("market_scraper.services.pipeline_steps.adaptive_rate_limiter", _fake_rate_limiter())
    monkeypatch.setattr("market_scraper.services.pipeline_steps.robots.is_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.get", MagicMock(return_value=None))
    monkeypatch.setattr("market_scraper.services.pipeline_steps.cache.set", MagicMock())
    async def fake_coalesce(key, coro):
        result = await coro()
        return result, True

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.singleflight.coalesce_with_leader",
        fake_coalesce,
    )
    monkeypatch.setattr("market_scraper.services.pipeline_steps.download_html", fake_download)
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps._response_classifier.classify",
        MagicMock(return_value=_classify_success()),
    )

    await step.run(context)

    assert captured["timeout"] == 12.5
