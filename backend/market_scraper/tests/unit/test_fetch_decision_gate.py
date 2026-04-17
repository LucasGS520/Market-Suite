"""Testes unitários para FetchDecisionGate.

FetchDecisionGate centraliza a lógica de aquisição em cascata:
  1. Rate limiter pré-check → REJECT imediato se bloqueado.
  2. Camada 1 (curl_cffi) via singleflight → HTTP 404/410/451 → REJECT com availability.
  3. ResponseClassifier avalia o resultado da camada 1.
  4. Se SCALE → Camada 3 (Playwright) com sinal anti-bot como telemetria.

Os testes isolam o gate mockando download_html, adaptive_rate_limiter, _classifier
e playwright_pool. Singleflight permanece real (sem I/O externo).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from market_scraper.services.fetch_decision_gate import (
    FetchDecisionGate,
    FetchResult,
    FetchStatus,
)
from market_scraper.services.playwright_pool import (
    PlaywrightFetchError,
    PlaywrightTimeoutError,
)
from market_scraper.services.response_classifier import (
    ClassificationAction,
    ClassificationResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# Constantes de fixture
# ─────────────────────────────────────────────────────────────────────────────

_URL = "https://www.mercadolivre.com.br/p/MLB123"
_DOMAIN = "www.mercadolivre.com.br"
_VALID_HTML = "<html><body>" + "x" * 2048 + "</body></html>"
_CHALLENGE_HTML = (
    "<html><head></head><body>"
    "<script src='https://challenges.cloudflare.com/turnstile/v0/api.js'></script>"
    + "x" * 2048
    + "</body></html>"
)
_CLEAN_PW_HTML = "<html><body>" + "produto válido " * 200 + "</body></html>"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_gate() -> FetchDecisionGate:
    return FetchDecisionGate()


def _rate_limiter_allow(monkeypatch) -> MagicMock:
    """Rate limiter que sempre permite a requisição."""
    rl = MagicMock()
    rl.should_allow = AsyncMock(return_value=(True, 1))
    rl.update_history = AsyncMock()
    monkeypatch.setattr("market_scraper.services.fetch_decision_gate.adaptive_rate_limiter", rl)
    return rl


def _rate_limiter_block(monkeypatch) -> MagicMock:
    """Rate limiter que sempre bloqueia a requisição."""
    rl = MagicMock()
    rl.should_allow = AsyncMock(return_value=(False, 0))
    rl.update_history = AsyncMock()
    monkeypatch.setattr("market_scraper.services.fetch_decision_gate.adaptive_rate_limiter", rl)
    return rl


def _mock_download(monkeypatch, html: str) -> AsyncMock:
    """download_html retorna HTML fixo."""
    mock = AsyncMock(return_value=html)
    monkeypatch.setattr("market_scraper.services.fetch_decision_gate.download_html", mock)
    return mock


def _mock_download_raises(monkeypatch, exc: Exception) -> AsyncMock:
    """download_html levanta a exceção informada."""
    mock = AsyncMock(side_effect=exc)
    monkeypatch.setattr("market_scraper.services.fetch_decision_gate.download_html", mock)
    return mock


def _mock_classifier(monkeypatch, result: ClassificationResult) -> MagicMock:
    cls = MagicMock()
    cls.classify = MagicMock(return_value=result)
    monkeypatch.setattr("market_scraper.services.fetch_decision_gate._classifier", cls)
    return cls


def _playwright_ready(monkeypatch, html: str) -> MagicMock:
    """playwright_pool pronto e retorna HTML."""
    pool = MagicMock()
    pool.is_ready = True
    pool.fetch_html = AsyncMock(return_value=html)
    monkeypatch.setattr("market_scraper.services.fetch_decision_gate.playwright_pool", pool)
    return pool


def _playwright_not_ready(monkeypatch) -> MagicMock:
    pool = MagicMock()
    pool.is_ready = False
    pool.fetch_html = AsyncMock(side_effect=AssertionError("não deveria ser chamado"))
    monkeypatch.setattr("market_scraper.services.fetch_decision_gate.playwright_pool", pool)
    return pool


def _playwright_raises(monkeypatch, exc: Exception) -> MagicMock:
    """playwright_pool pronto mas lança exceção ao fetch."""
    pool = MagicMock()
    pool.is_ready = True
    pool.fetch_html = AsyncMock(side_effect=exc)
    monkeypatch.setattr("market_scraper.services.fetch_decision_gate.playwright_pool", pool)
    return pool


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    response = MagicMock()
    response.status_code = status_code
    return httpx.HTTPStatusError(
        message=f"HTTP {status_code}",
        request=MagicMock(),
        response=response,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Caso 1 — Sucesso via curl_cffi (camada 1)
# ─────────────────────────────────────────────────────────────────────────────

async def test_gate_layer1_success(monkeypatch):
    """curl_cffi retorna HTML válido → SUCCESS com layer_used=curl_cffi."""
    gate = _make_gate()
    _rate_limiter_allow(monkeypatch)
    _mock_download(monkeypatch, _VALID_HTML)
    _mock_classifier(
        monkeypatch,
        ClassificationResult(action=ClassificationAction.SUCCESS, next_layer=None, reason="html_valid"),
    )
    _playwright_not_ready(monkeypatch)

    result = await gate.fetch_with_fallback(_URL, domain=_DOMAIN, force_refresh=False, http_timeout=5.0, browser_timeout=10.0)

    assert result.status == FetchStatus.SUCCESS
    assert result.html == _VALID_HTML
    assert result.layer_used == "curl_cffi"
    assert result.fallback_taken is False
    assert result.http_status == 200
    assert result.classification_reason == "html_valid"


# ─────────────────────────────────────────────────────────────────────────────
# Caso 2 — Challenge anti-bot → Playwright resolve
# ─────────────────────────────────────────────────────────────────────────────

async def test_gate_layer1_challenge_playwright_succeeds(monkeypatch):
    """curl_cffi retorna página de challenge → classificador escala → Playwright entrega HTML limpo.

    Expectativa: SUCCESS_AFTER_BROWSER, anti_bot_detected=True, anti_bot_bypassed=True,
    padrão residual ausente no HTML final.
    """
    gate = _make_gate()
    _rate_limiter_allow(monkeypatch)
    _mock_download(monkeypatch, _CHALLENGE_HTML)
    _mock_classifier(
        monkeypatch,
        ClassificationResult(
            action=ClassificationAction.SCALE,
            next_layer=3,
            reason="anti_bot_page",
            telemetry={"anti_bot_pattern": "cloudflare_challenge"},
        ),
    )
    _playwright_ready(monkeypatch, _CLEAN_PW_HTML)

    result = await gate.fetch_with_fallback(_URL, domain=_DOMAIN, force_refresh=False, http_timeout=5.0, browser_timeout=10.0)

    assert result.status == FetchStatus.SUCCESS_AFTER_BROWSER
    assert result.html == _CLEAN_PW_HTML
    assert result.layer_used == "playwright"
    assert result.fallback_taken is True
    assert result.anti_bot_detected is True
    assert result.anti_bot_bypassed is True      # Playwright resolveu; sem padrão residual
    assert result.http_status == 200


# ─────────────────────────────────────────────────────────────────────────────
# Caso 3 — HTTP 404 → REJECT com availability inferida
# ─────────────────────────────────────────────────────────────────────────────

async def test_gate_http_404_rejects_with_availability(monkeypatch):
    """curl_cffi levanta HTTPStatusError(404) → gate rejeita sem acionar Playwright.

    Produto definitivamente indisponível: availability=False, last_status='removed'.
    """
    gate = _make_gate()
    _rate_limiter_allow(monkeypatch)
    _mock_download_raises(monkeypatch, _http_status_error(404))
    # Classifier não deve ser chamado para status em HTTP_STATUS_UNAVAILABLE
    cls_mock = MagicMock()
    cls_mock.classify = MagicMock(side_effect=AssertionError("classifier não deveria ser chamado"))
    monkeypatch.setattr("market_scraper.services.fetch_decision_gate._classifier", cls_mock)
    _playwright_not_ready(monkeypatch)

    result = await gate.fetch_with_fallback(_URL, domain=_DOMAIN, force_refresh=False, http_timeout=5.0, browser_timeout=10.0)

    assert result.status == FetchStatus.REJECT
    assert result.error_code == "product_unavailable"
    assert result.availability is False
    assert result.last_status == "removed"
    assert result.http_status == 404
    assert result.html is None


# ─────────────────────────────────────────────────────────────────────────────
# Caso 4 — Playwright timeout após escalonamento
# ─────────────────────────────────────────────────────────────────────────────

async def test_gate_playwright_timeout(monkeypatch):
    """Classificador escala para Playwright; Playwright lança timeout → REJECT_AFTER_BROWSER."""
    gate = _make_gate()
    _rate_limiter_allow(monkeypatch)
    _mock_download(monkeypatch, _CHALLENGE_HTML)
    _mock_classifier(
        monkeypatch,
        ClassificationResult(
            action=ClassificationAction.SCALE,
            next_layer=3,
            reason="anti_bot_page",
            telemetry={"anti_bot_pattern": "cloudflare_challenge"},
        ),
    )
    _playwright_raises(
        monkeypatch,
        PlaywrightTimeoutError(url=_URL, timeout=5.0),
    )

    result = await gate.fetch_with_fallback(_URL, domain=_DOMAIN, force_refresh=False, http_timeout=5.0, browser_timeout=10.0)

    assert result.status == FetchStatus.REJECT_AFTER_BROWSER
    assert result.error_code == "playwright_timeout"
    assert result.classification_reason == "anti_bot_page"
    assert result.html is None


# ─────────────────────────────────────────────────────────────────────────────
# Caso 5 — Anti-bot com sinais de produto → SUCCESS degradado (sem Playwright)
# ─────────────────────────────────────────────────────────────────────────────

async def test_gate_anti_bot_degraded_returns_success_without_playwright(monkeypatch):
    """Classificador retorna SUCCESS(anti_bot_degraded) → gate retorna SUCCESS com
    telemetria anti-bot propagada; Playwright não é acionado.
    """
    gate = _make_gate()
    _rate_limiter_allow(monkeypatch)
    _mock_download(monkeypatch, _VALID_HTML)
    _mock_classifier(
        monkeypatch,
        ClassificationResult(
            action=ClassificationAction.SUCCESS,
            next_layer=None,
            reason="anti_bot_degraded",
            telemetry={"anti_bot_pattern": "cloudflare_challenge"},
        ),
    )
    _playwright_not_ready(monkeypatch)  # garante que Playwright não é chamado

    result = await gate.fetch_with_fallback(
        _URL, domain=_DOMAIN, force_refresh=False, http_timeout=5.0, browser_timeout=10.0
    )

    assert result.status == FetchStatus.SUCCESS
    assert result.html == _VALID_HTML
    assert result.layer_used == "curl_cffi"
    assert result.fallback_taken is False
    assert result.anti_bot_detected is True
    assert result.anti_bot_pattern == "cloudflare_challenge"
    assert result.anti_bot_bypassed is False
    assert result.classification_reason == "anti_bot_degraded"


# ─────────────────────────────────────────────────────────────────────────────
# Caso 6 — Rate limiter bloqueia antes de qualquer download
# ─────────────────────────────────────────────────────────────────────────────

async def test_gate_rate_limiter_blocks(monkeypatch):
    """Rate limiter retorna (False, 0) → REJECT imediato quando BLOCK_ENABLED=True."""
    import market_scraper.services.fetch_decision_gate as _fds_module
    monkeypatch.setattr(_fds_module.settings, "SCRAPER_RATE_LIMITER_BLOCK_ENABLED", True)

    gate = _make_gate()
    _rate_limiter_block(monkeypatch)

    download_mock = AsyncMock(side_effect=AssertionError("download não deveria ser chamado"))
    monkeypatch.setattr("market_scraper.services.fetch_decision_gate.download_html", download_mock)

    result = await gate.fetch_with_fallback(_URL, domain=_DOMAIN, force_refresh=False, http_timeout=5.0, browser_timeout=10.0)

    assert result.status == FetchStatus.REJECT
    assert result.error_code == "rate_limiter_cooldown"
    assert result.html is None
    download_mock.assert_not_called()
