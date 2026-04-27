"""Testes unitários para CrawleeRuntime.

Valida os quatro caminhos da política de coleta:
    ACCEPT           → CollectedDocument com html, layer_used="http"
    STOP_UNAVAILABLE → CollectedDocument com html=None, 1 tentativa http failure
    STOP_FAILURE     → CollectedDocument com html=None, sem acionar browser
    ESCALATE         → CollectedDocument com browser fallback, 2 tentativas
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from market_scraper.collection.crawler.crawlee_runtime import CrawleeRuntime
from market_scraper.collection.dto.collected_document import CollectedDocument
from market_scraper.collection.policy import CollectionDecision, CollectionPolicyAction


# ── Fixtures ──────────────────────────────────────────────────────────────────

_VALID_HTML = "<html><body>" + "x" * 3000 + "</body></html>"
_BROWSER_HTML = "<html><body>" + "y" * 3000 + "</body></html>"


def _make_runtime(
    *,
    http_html: str | None = _VALID_HTML,
    http_exc: Exception | None = None,
    browser_html: str | None = _BROWSER_HTML,
    browser_exc: Exception | None = None,
    policy_decision: CollectionDecision | None = None,
) -> CrawleeRuntime:
    http_mock = AsyncMock()
    if http_exc is not None:
        http_mock.fetch.side_effect = http_exc
    else:
        http_mock.fetch.return_value = http_html

    browser_mock = AsyncMock()
    browser_mock.is_ready = True
    if browser_exc is not None:
        browser_mock.fetch.side_effect = browser_exc
    else:
        browser_mock.fetch.return_value = browser_html

    policy_mock = MagicMock()
    if policy_decision is not None:
        policy_mock.classify.return_value = policy_decision
    else:
        policy_mock.classify.return_value = CollectionDecision(
            action=CollectionPolicyAction.ACCEPT,
            reason="html_ok",
            telemetry={},
        )

    return CrawleeRuntime(
        http_collector=http_mock,
        browser_collector=browser_mock,
        policy=policy_mock,
    )


# ── ACCEPT via HTTP ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_accept_returns_document_with_http_html():
    runtime = _make_runtime(
        http_html=_VALID_HTML,
        policy_decision=CollectionDecision(
            action=CollectionPolicyAction.ACCEPT,
            reason="html_ok",
            telemetry={},
        ),
    )
    doc = await runtime.fetch_with_fallback("https://exemplo.com/produto/1")

    assert isinstance(doc, CollectedDocument)
    assert doc.html == _VALID_HTML
    assert doc.layer_used == "http"
    assert doc.fallback_taken is False
    assert doc.is_successful is True
    assert len(doc.attempts) == 1
    assert doc.attempts[0].layer == "http"
    assert doc.attempts[0].status == "success"


@pytest.mark.asyncio
async def test_accept_with_anti_bot_in_telemetry():
    runtime = _make_runtime(
        policy_decision=CollectionDecision(
            action=CollectionPolicyAction.ACCEPT,
            reason="anti_bot_degraded",
            telemetry={"anti_bot_pattern": "cloudflare_challenge"},
        ),
    )
    doc = await runtime.fetch_with_fallback("https://exemplo.com/produto/1")

    assert doc.anti_bot_detected is True
    assert doc.anti_bot_pattern == "cloudflare_challenge"
    assert doc.data_quality == "degraded_anti_bot"  # sem fallback mas com anti-bot detectado


# ── STOP_UNAVAILABLE ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stop_unavailable_returns_no_html_without_browser():
    http_exc = httpx.HTTPStatusError(
        "HTTP 404",
        request=httpx.Request("GET", "https://exemplo.com/produto/1"),
        response=httpx.Response(404),
    )
    runtime = _make_runtime(
        http_exc=http_exc,
        policy_decision=CollectionDecision(
            action=CollectionPolicyAction.STOP_UNAVAILABLE,
            reason="http_404_unavailable",
            telemetry={"http_status": 404},
        ),
    )
    doc = await runtime.fetch_with_fallback("https://exemplo.com/produto/1")

    assert doc.html is None
    assert doc.is_successful is False
    assert doc.fallback_taken is False
    assert len(doc.attempts) == 1
    assert doc.attempts[0].status == "failure"
    assert "404" in doc.attempts[0].error_code

    # browser NÃO deve ter sido acionado
    runtime._browser.fetch.assert_not_awaited()  # type: ignore[attr-defined]


# ── STOP_FAILURE ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stop_failure_returns_no_html_without_browser():
    runtime = _make_runtime(
        http_html=None,
        policy_decision=CollectionDecision(
            action=CollectionPolicyAction.STOP_FAILURE,
            reason="connection_error",
            telemetry={},
        ),
    )
    doc = await runtime.fetch_with_fallback("https://exemplo.com/produto/1")

    assert doc.html is None
    assert doc.is_successful is False
    assert doc.fallback_taken is False
    assert len(doc.attempts) == 1
    assert doc.attempts[0].status == "failure"

    runtime._browser.fetch.assert_not_awaited()  # type: ignore[attr-defined]


# ── ESCALATE_TO_BROWSER ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_escalate_uses_browser_and_marks_fallback():
    runtime = _make_runtime(
        http_html="<html></html>",
        browser_html=_BROWSER_HTML,
        policy_decision=CollectionDecision(
            action=CollectionPolicyAction.ESCALATE_TO_BROWSER,
            reason="html_empty",
            telemetry={},
        ),
    )
    doc = await runtime.fetch_with_fallback(
        "https://exemplo.com/produto/1", domain="exemplo.com"
    )

    assert doc.html == _BROWSER_HTML
    assert doc.layer_used == "browser"
    assert doc.fallback_taken is True
    assert doc.data_quality == "browser_fallback"
    assert len(doc.attempts) == 2
    assert doc.attempts[0].layer == "http"
    assert doc.attempts[0].status == "escalated"
    assert doc.attempts[1].layer == "browser"
    assert doc.attempts[1].status == "success"


@pytest.mark.asyncio
async def test_escalate_browser_failure_returns_no_html():
    runtime = _make_runtime(
        http_html="<html></html>",
        browser_exc=RuntimeError("browser crash"),
        policy_decision=CollectionDecision(
            action=CollectionPolicyAction.ESCALATE_TO_BROWSER,
            reason="html_empty",
            telemetry={},
        ),
    )
    doc = await runtime.fetch_with_fallback("https://exemplo.com/produto/1")

    assert doc.html is None
    assert doc.is_successful is False
    assert doc.fallback_taken is True
    assert len(doc.attempts) == 2
    assert doc.attempts[1].status == "failure"
    assert doc.attempts[1].error_code == "RuntimeError"


# ── Telemetria de tempo ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duration_ms_is_positive():
    runtime = _make_runtime()
    doc = await runtime.fetch_with_fallback("https://exemplo.com/produto/1")
    assert doc.duration_ms > 0


@pytest.mark.asyncio
async def test_timestamp_is_recent():
    import time
    before = time.time()
    runtime = _make_runtime()
    doc = await runtime.fetch_with_fallback("https://exemplo.com/produto/1")
    after = time.time()
    assert before <= doc.timestamp <= after


# ── Fixture anti-bot: detecção residual após browser ─────────────────────────

@pytest.mark.asyncio
async def test_browser_residual_antibot_detected():
    """Browser retorna HTML mas com marcador anti-bot residual."""
    browser_html_with_antibot = (
        "<html><body>__cf_chl_opt={}" + "x" * 2000 + "</body></html>"
    )
    runtime = _make_runtime(
        http_html="<html></html>",
        browser_html=browser_html_with_antibot,
        policy_decision=CollectionDecision(
            action=CollectionPolicyAction.ESCALATE_TO_BROWSER,
            reason="html_empty",
            telemetry={},
        ),
    )

    with patch(
        "market_scraper.collection.crawler.crawlee_runtime.detect_anti_bot_pattern",
        return_value="cloudflare_challenge",
    ):
        doc = await runtime.fetch_with_fallback("https://exemplo.com/produto/1")

    assert doc.anti_bot_detected is True
    assert doc.anti_bot_pattern == "cloudflare_challenge"
    assert doc.data_quality == "browser_fallback"
