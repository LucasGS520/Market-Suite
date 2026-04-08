from __future__ import annotations

import asyncio
from decimal import Decimal

import httpx
from shared.schemas.shared_schemas_scraper import ParserResponse
from shared.utils.url_validation import UrlIssue

from market_scraper.services.synergic_pipeline import PipelineStep, StepResult


def test_parse_flow_returns_success_with_shared_contract(
    integration_client,
    monkeypatch,
    success_product_html,
):
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    async def fake_download(url: str, *, timeout: float) -> str:
        return success_product_html

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.download_html",
        fake_download,
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


def test_parse_flow_returns_304_when_cached_response_matches_conditionals(
    integration_client,
    monkeypatch,
    success_product_html,
):
    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    async def fake_download(url: str, *, timeout: float) -> str:
        return success_product_html

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.download_html",
        fake_download,
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
        return success_product_html

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.download_html",
        fake_download,
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
        "market_scraper.services.pipeline_steps.download_html",
        fake_download,
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

    async def fake_download(url: str, *, timeout: float) -> str:
        return "<html><body><p>sem nome e sem preco</p></body></html>"

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.resolve_public_address",
        lambda host: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.download_html",
        fake_download,
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
