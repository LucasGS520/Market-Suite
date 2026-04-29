from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from shared.schemas.shared_schemas_scraper import ParserResponse
from shared.utils.url_validation import UrlIssue

from market_scraper.services.response_classifier import (
    ClassificationAction,
    ClassificationResult,
)
from market_scraper.collection.dto.collected_document import CollectedDocument
from market_scraper.collection.dto.collection_attempt import CollectionAttempt


def _fake_rate_limiter() -> MagicMock:
    rl = MagicMock()
    rl.should_allow = AsyncMock(return_value=(True, 1))
    rl.update_history = AsyncMock()
    return rl


def _fake_classifier_success() -> MagicMock:
    cls = MagicMock()
    cls.classify = MagicMock(
        return_value=ClassificationResult(
            action=ClassificationAction.SUCCESS,
            next_layer=None,
            reason="html_valid",
        )
    )
    return cls


def _fake_classifier_antibot() -> MagicMock:
    cls = MagicMock()
    cls.classify = MagicMock(
        return_value=ClassificationResult(
            action=ClassificationAction.SCALE,
            next_layer=3,
            reason="anti_bot_page",
            telemetry={"anti_bot_pattern": "cloudflare_challenge"},
        )
    )
    return cls


def _pad_html(html: str) -> str:
    return html + "<!--" + ("x" * 2048) + "-->"


def _collected_document(
    *,
    html: str | None,
    http_status: int | None = 200,
    layer_used: str = "curl_cffi",
    fallback_taken: bool = False,
    classification_reason: str | None = "html_valid",
    anti_bot_detected: bool = False,
    anti_bot_pattern: str | None = None,
    anti_bot_bypassed: bool = False,
    error_code: str | None = None,
) -> CollectedDocument:
    return CollectedDocument(
        html=html,
        http_status=http_status,
        headers={},
        layer_used=layer_used,
        fallback_taken=fallback_taken,
        anti_bot_detected=anti_bot_detected,
        anti_bot_pattern=anti_bot_pattern,
        timestamp=time.time(),
        duration_ms=1.0,
        attempts=(
            CollectionAttempt(
                layer=layer_used,
                status="success" if html else "failure",
                error_code=error_code,
                duration_ms=1.0,
                reason=classification_reason,
            ),
        ),
        error_code=error_code,
        classification_reason=classification_reason,
        anti_bot_bypassed=anti_bot_bypassed,
    )


def _stub_runtime(monkeypatch, document: CollectedDocument):
    runtime = MagicMock()
    runtime.fetch_with_fallback = AsyncMock(return_value=document)
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product.get_crawlee_runtime",
        lambda: runtime,
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product.adaptive_rate_limiter",
        _fake_rate_limiter(),
    )
    return runtime


def test_parse_flow_returns_success_with_shared_contract(
    integration_client,
    monkeypatch,
    success_product_html,
):
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product._robots.is_allowed",
        fake_is_allowed,
    )
    _stub_runtime(
        monkeypatch,
        _collected_document(html=_pad_html(success_product_html)),
    )

    response = integration_client.post("/scraper/parse", json={"url": "example.com/product/1"})

    assert response.status_code == 200
    assert response.headers["x-marketscraper-cache-status"] == "miss"

    payload = ParserResponse.model_validate(response.json())
    assert payload.name == "Notebook Integrado"
    assert payload.current_price == Decimal("1999.90")
    assert payload.currency is None
    assert str(payload.url) == "https://example.com/product/1"
    assert payload.source == "example.com"
    assert payload.payload == {
        "acquisition": {
            "layer_used": "curl_cffi",
            "fallback_taken": False,
            "classification_reason": "html_valid",
            "http_status": 200,
            "anti_bot_detected": False,
            "anti_bot_pattern": None,
            "anti_bot_bypassed": False,
            "data_quality": "normal",
        }
    }


def test_parse_flow_returns_304_when_cached_response_matches_conditionals(
    integration_client,
    monkeypatch,
    success_product_html,
):
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product._robots.is_allowed",
        fake_is_allowed,
    )
    _stub_runtime(
        monkeypatch,
        _collected_document(html=_pad_html(success_product_html)),
    )

    first = integration_client.post("/scraper/parse", json={"url": "example.com/product/304"})
    assert first.status_code == 200
    etag = first.headers["etag"]
    last_modified = first.headers["last-modified"]

    second = integration_client.post(
        "/scraper/parse",
        json={"url": "example.com/product/304"},
        headers={
            "if-none-match": etag,
            "if-modified-since": last_modified,
        },
    )

    assert second.status_code == 304
    assert second.headers["etag"] == etag
    assert second.headers["x-marketscraper-cache-status"] == "hit"


def test_parse_flow_force_refresh_bypasses_http_and_pipeline_cache(
    integration_client,
    monkeypatch,
    success_product_html,
):
    calls = {"download": 0}

    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product._robots.is_allowed",
        fake_is_allowed,
    )
    runtime = _stub_runtime(monkeypatch, _collected_document(html=_pad_html(success_product_html)))

    async def fake_fetch(*args, **kwargs):
        calls["download"] += 1
        return _collected_document(html=_pad_html(success_product_html))

    runtime.fetch_with_fallback.side_effect = fake_fetch

    first = integration_client.post("/scraper/parse", json={"url": "example.com/product/cache"})
    second = integration_client.post(
        "/scraper/parse",
        json={
            "url": "example.com/product/cache",
            "metadata": {"force_refresh": True},
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers["x-marketscraper-cache-status"] == "bypass"
    assert calls["download"] == 2


def test_parse_flow_returns_invalid_url_for_embedded_credentials(integration_client):
    response = integration_client.post(
        "/scraper/parse",
        json={"url": "https://user:pass@example.com/product"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_url"


def test_parse_flow_returns_blocked_host_when_public_resolution_fails(
    integration_client,
    monkeypatch,
):
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper._ensure_public_endpoint",
        lambda host: UrlIssue(code="blocked_host", message="Host bloqueado"),
    )

    response = integration_client.post("/scraper/parse", json={"url": "https://example.com/product"})

    assert response.status_code == 400
    assert response.json()["error_code"] == "blocked_host"


def test_parse_flow_returns_robots_disallowed(
    integration_client,
    monkeypatch,
):
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return False

    import market_scraper.scraper_orchestrator.parse_product as _orch_mod
    monkeypatch.setattr(_orch_mod.settings, "SCRAPER_ROBOTS_MODE", "block")
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product._robots.is_allowed",
        fake_is_allowed,
    )

    response = integration_client.post("/scraper/parse", json={"url": "https://example.com/product"})

    assert response.status_code == 403
    assert response.json()["error_code"] == "robots_disallowed"


def test_parse_flow_returns_too_many_redirects(
    integration_client,
    monkeypatch,
):
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product._robots.is_allowed",
        fake_is_allowed,
    )
    _stub_runtime(
        monkeypatch,
        _collected_document(
            html=None,
            http_status=None,
            layer_used="curl_cffi",
            classification_reason="too_many_redirects",
            error_code="too_many_redirects",
        ),
    )

    response = integration_client.post("/scraper/parse", json={"url": "https://example.com/product"})

    assert response.status_code == 422
    assert response.json()["error_code"] == "too_many_redirects"


def test_parse_flow_returns_no_result_when_pipeline_cannot_extract_data(
    integration_client,
    monkeypatch,
):
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    _empty_html = _pad_html("<html><body><p>sem nome e sem preco</p></body></html>")

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product._robots.is_allowed",
        fake_is_allowed,
    )
    _stub_runtime(monkeypatch, _collected_document(html=_empty_html))

    response = integration_client.post("/scraper/parse", json={"url": "https://example.com/product"})

    assert response.status_code == 422
    assert response.json()["error_code"] == "no_result"


def test_parse_flow_returns_pipeline_timeout(
    integration_client,
    monkeypatch,
):
    import market_scraper.scraper_orchestrator.parse_product as _orch_mod

    class _AsyncioStub:
        TimeoutError = asyncio.TimeoutError

        @staticmethod
        async def wait_for(coro, timeout):
            try:
                coro.close()
            except Exception:
                pass
            raise asyncio.TimeoutError()

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product._robots.is_allowed",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(_orch_mod, "asyncio", _AsyncioStub)

    response = integration_client.post("/scraper/parse", json={"url": "https://example.com/product"})

    assert response.status_code == 504
    assert response.json()["error_code"] == "pipeline_timeout"


def test_parse_flow_normalizes_degraded_success_payload_without_breaking_contract(
    integration_client,
    monkeypatch,
):
    from market_scraper.scraper_orchestrator.parse_product import ParseProductSuccess

    parser_response = ParserResponse(
        name="Produto degradado",
        current_price=None,
        url="https://example.com/product/degraded",
        source="fallback.example.com",
        last_status="temporarily_unavailable",
        payload={"sku": "SKU-9"},
    )
    result = ParseProductSuccess(kind="success", parser_response=parser_response, stage_timings={})

    async def fake_execute(self, *args, **kwargs):
        return result

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product.ParseProduct.execute",
        fake_execute,
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.store_response",
        lambda url, resp: None,
    )

    response = integration_client.post("/scraper/parse", json={"url": "example.com/product/degraded"})

    assert response.status_code == 200
    assert response.headers["x-marketscraper-cache-status"] == "miss"
    payload = ParserResponse.model_validate(response.json())
    assert payload.name == "Produto degradado"
    assert payload.current_price is None
    assert payload.last_status == "temporarily_unavailable"
    assert payload.source == "fallback.example.com"
    assert payload.payload == {"sku": "SKU-9"}


def test_parse_flow_exposes_acquisition_payload_after_playwright_fallback(
    integration_client,
    monkeypatch,
    success_product_html,
):
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product._robots.is_allowed",
        fake_is_allowed,
    )
    _stub_runtime(
        monkeypatch,
        _collected_document(
            html=success_product_html,
            layer_used="playwright",
            fallback_taken=True,
            classification_reason="anti_bot_page",
            anti_bot_detected=True,
            anti_bot_pattern="cloudflare_challenge",
            anti_bot_bypassed=True,
        ),
    )

    response = integration_client.post("/scraper/parse", json={"url": "example.com/product/challenge"})

    assert response.status_code == 200
    payload = ParserResponse.model_validate(response.json())
    assert payload.payload == {
        "acquisition": {
            "layer_used": "playwright",
            "fallback_taken": True,
            "classification_reason": "anti_bot_page",
            "http_status": 200,
            "anti_bot_detected": True,
            "anti_bot_pattern": "cloudflare_challenge",
            "anti_bot_bypassed": True,
            "data_quality": "browser_fallback",
        }
    }


def test_parse_flow_exposes_acquisition_payload_for_unavailable_product(
    integration_client,
    monkeypatch,
):
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product._robots.is_allowed",
        fake_is_allowed,
    )
    _stub_runtime(
        monkeypatch,
        _collected_document(
            html=None,
            http_status=404,
            layer_used=None,
            classification_reason=None,
        ),
    )

    response = integration_client.post("/scraper/parse", json={"url": "example.com/product/missing"})

    assert response.status_code == 200
    payload = ParserResponse.model_validate(response.json())
    assert payload.availability is False
    assert payload.last_status == "removed"
    assert payload.payload == {
        "acquisition": {
            "layer_used": None,
            "fallback_taken": False,
            "classification_reason": None,
            "http_status": 404,
            "anti_bot_detected": False,
            "anti_bot_pattern": None,
            "anti_bot_bypassed": False,
            "data_quality": "normal",
        }
    }


def test_parse_flow_returns_429_when_anti_bot_page_detected(
    integration_client,
    monkeypatch,
):
    """429 quando o runtime sinaliza página de proteção anti-bot não contornável."""

    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product._robots.is_allowed",
        fake_is_allowed,
    )
    _stub_runtime(
        monkeypatch,
        _collected_document(
            html=None,
            http_status=None,
            layer_used="playwright",
            fallback_taken=True,
            classification_reason="anti_bot_page",
            anti_bot_detected=True,
            anti_bot_pattern="cloudflare_challenge",
            error_code="anti_bot_page",
        ),
    )

    response = integration_client.post("/scraper/parse", json={"url": "example.com/product/blocked"})

    assert response.status_code == 429
    body = response.json()
    assert body["error_code"] == "anti_bot_page"
    assert "trace_id" in body


def test_parse_flow_returns_503_when_playwright_fetch_fails(
    integration_client,
    monkeypatch,
):
    """503 quando o browser falha ao buscar conteúdo (playwright_fetch_error)."""

    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product._robots.is_allowed",
        fake_is_allowed,
    )
    _stub_runtime(
        monkeypatch,
        _collected_document(
            html=None,
            http_status=None,
            layer_used="playwright",
            fallback_taken=True,
            classification_reason="playwright_fetch_error",
            error_code="playwright_fetch_error",
        ),
    )

    response = integration_client.post("/scraper/parse", json={"url": "example.com/product/playwrightfail"})

    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "playwright_fetch_error"
    assert "trace_id" in body


def test_parse_flow_returns_503_when_playwright_not_ready(
    integration_client,
    monkeypatch,
):
    """503 quando o pool de browser não está disponível (playwright_not_ready → pipeline_degraded)."""

    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product._robots.is_allowed",
        fake_is_allowed,
    )
    _stub_runtime(
        monkeypatch,
        _collected_document(
            html=None,
            http_status=None,
            layer_used="playwright",
            fallback_taken=True,
            classification_reason="playwright_not_ready",
            error_code="playwright_not_ready",
        ),
    )

    response = integration_client.post("/scraper/parse", json={"url": "example.com/product/notready"})

    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "pipeline_degraded"
    assert "trace_id" in body


# ─────────────────────────────────────────────────────────────────────────────
# Regressão Fase 2/3 — novos caminhos de browser e fixtures reais
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_flow_returns_504_when_playwright_times_out(
    integration_client,
    monkeypatch,
):
    """504 quando browser Playwright atinge timeout (playwright_timeout).

    Regressão: garante mapeamento correto de playwright_timeout → HTTP 504.
    """
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product._robots.is_allowed",
        fake_is_allowed,
    )
    _stub_runtime(
        monkeypatch,
        _collected_document(
            html=None,
            http_status=None,
            layer_used="playwright",
            fallback_taken=True,
            classification_reason="browser_timeout",
            error_code="playwright_timeout",
        ),
    )

    response = integration_client.post("/scraper/parse", json={"url": "example.com/product/timeout"})

    assert response.status_code == 504
    body = response.json()
    assert body["error_code"] == "playwright_timeout"
    assert "trace_id" in body


def test_parse_flow_returns_success_with_browser_fallback_and_product_fixture(
    integration_client,
    monkeypatch,
    success_product_html,
):
    """Browser fallback com product_success.html → 200 com dados extraídos e acquisition correto.

    Regressão: garante que classification_reason='browser_fetch_success' (Fase 2)
    é propagado corretamente para o payload de aquisição.
    """
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product._robots.is_allowed",
        fake_is_allowed,
    )
    _stub_runtime(
        monkeypatch,
        _collected_document(
            html=_pad_html(success_product_html),
            http_status=200,
            layer_used="playwright",
            fallback_taken=True,
            classification_reason="browser_fetch_success",
            anti_bot_bypassed=True,
        ),
    )

    response = integration_client.post(
        "/scraper/parse", json={"url": "example.com/product/browser-fallback"}
    )

    assert response.status_code == 200
    payload = ParserResponse.model_validate(response.json())
    assert payload.name == "Notebook Integrado"
    assert payload.current_price == Decimal("1999.90")
    acq = payload.payload["acquisition"]
    assert acq["layer_used"] == "playwright"
    assert acq["fallback_taken"] is True
    assert acq["classification_reason"] == "browser_fetch_success"
    assert acq["anti_bot_bypassed"] is True
