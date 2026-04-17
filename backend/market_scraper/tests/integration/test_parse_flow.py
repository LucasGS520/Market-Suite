from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
from shared.schemas.shared_schemas_scraper import ParserResponse
from shared.utils.url_validation import UrlIssue

from market_scraper.services.response_classifier import (
    ClassificationAction,
    ClassificationResult,
)
from market_scraper.services.synergic_pipeline import (
    PipelineContext,
    PipelineOutcome,
    PipelineStep,
    StepResult,
)


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


def test_parse_flow_returns_success_with_shared_contract(
    integration_client,
    monkeypatch,
    success_product_html,
):
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    async def fake_download(url: str, *, timeout: float) -> str:
        return _pad_html(success_product_html)

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.download_html",
        fake_download,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.adaptive_rate_limiter",
        _fake_rate_limiter(),
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate._classifier",
        _fake_classifier_success(),
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

    async def fake_download(url: str, *, timeout: float) -> str:
        return _pad_html(success_product_html)

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.download_html",
        fake_download,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.adaptive_rate_limiter",
        _fake_rate_limiter(),
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate._classifier",
        _fake_classifier_success(),
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

    async def fake_download(url: str, *, timeout: float) -> str:
        calls["download"] += 1
        return _pad_html(success_product_html)

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.download_html",
        fake_download,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.adaptive_rate_limiter",
        _fake_rate_limiter(),
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate._classifier",
        _fake_classifier_success(),
    )

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


def test_parse_flow_returns_unsupported_by_robots(
    integration_client,
    monkeypatch,
):
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return False

    import market_scraper.services.pipeline_steps as _ps_module
    monkeypatch.setattr(_ps_module.settings, "SCRAPER_ROBOTS_MODE", "block")
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )

    response = integration_client.post("/scraper/parse", json={"url": "https://example.com/product"})

    assert response.status_code == 403
    assert response.json()["error_code"] == "unsupported_by_robots"


def test_parse_flow_returns_too_many_redirects(
    integration_client,
    monkeypatch,
):
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    async def fake_download(url: str, *, timeout: float) -> str:
        request = httpx.Request("GET", url)
        raise httpx.TooManyRedirects("redirect loop", request=request)

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.download_html",
        fake_download,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.adaptive_rate_limiter",
        _fake_rate_limiter(),
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate._classifier",
        _fake_classifier_success(),
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

    async def fake_download(url: str, *, timeout: float) -> str:
        return _empty_html

    # Late browser escalation fires after parsers fail; mock Playwright to also return
    # HTML without useful data so the pipeline ends correctly with no_result.
    fake_pw_pool = MagicMock()
    fake_pw_pool.is_ready = True
    fake_pw_pool.fetch_html = AsyncMock(return_value=_empty_html)

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.download_html",
        fake_download,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.adaptive_rate_limiter",
        _fake_rate_limiter(),
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.playwright_pool",
        fake_pw_pool,
    )

    response = integration_client.post("/scraper/parse", json={"url": "https://example.com/product"})

    assert response.status_code == 422
    assert response.json()["error_code"] == "no_result"


def test_parse_flow_returns_pipeline_timeout(
    integration_client,
    monkeypatch,
):
    class SlowStep(PipelineStep):
        def __init__(self) -> None:
            super().__init__(name="slow-step", timeout=1.0)

        async def run(self, context):
            await asyncio.sleep(0.05)
            return StepResult.empty("slow-step-finished")

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_factory.default_pipeline_steps",
        lambda: [SlowStep()],
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_factory.settings",
        type(
            "SettingsStub",
            (),
            {
                "SCRAPER_STEP_TIMEOUT_SECONDS": 1.0,
                "SCRAPER_PIPELINE_TIMEOUT_SECONDS": 0.01,
            },
        )(),
    )

    response = integration_client.post("/scraper/parse", json={"url": "https://example.com/product"})

    assert response.status_code == 504
    assert response.json()["error_code"] == "pipeline_timeout"


def test_parse_flow_normalizes_degraded_success_payload_without_breaking_contract(
    integration_client,
    monkeypatch,
):
    context = PipelineContext(
        url="https://example.com/product/degraded",
        source="example.com",
        default_step_timeout=1.0,
        trace_id="trace-contract",
    )
    context.data["last_status"] = "temporarily_unavailable"

    async def fake_run_pipeline(url: str, *, force_refresh: bool = False, trace_id: str | None = None):
        assert url == "https://example.com/product/degraded"
        assert trace_id is not None
        return PipelineOutcome(
            status="success",
            context=context,
            payload={
                "name": "Produto degradado",
                "current_price": "preco invalido",
                "source": None,
                "marketplace": "fallback.example.com",
                "sku": "SKU-9",
            },
        )

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.run_pipeline",
        fake_run_pipeline,
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
    fixture_html_loader,
):
    challenge_html = _pad_html(fixture_html_loader("response_js_challenge.html"))

    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    async def fake_download(url: str, *, timeout: float) -> str:
        return challenge_html

    fake_pw_pool = type(
        "PoolStub",
        (),
        {
            "is_ready": True,
            "fetch_html": AsyncMock(return_value=success_product_html),
        },
    )()

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.download_html",
        fake_download,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.adaptive_rate_limiter",
        _fake_rate_limiter(),
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate._classifier",
        _fake_classifier_antibot(),
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.playwright_pool",
        fake_pw_pool,
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

    async def fake_download(url: str, *, timeout: float) -> str:
        request = httpx.Request("GET", url)
        response = httpx.Response(status_code=404, request=request)
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.download_html",
        fake_download,
    )
    monkeypatch.setattr(
        "market_scraper.services.fetch_decision_gate.adaptive_rate_limiter",
        _fake_rate_limiter(),
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
