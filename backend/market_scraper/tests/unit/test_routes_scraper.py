from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from shared.schemas import ParserResponse
from shared.schemas.shared_schemas_scraper import (
    SCRAPER_CONTRACT_VERSION,
    SCRAPER_CONTRACT_VERSION_HEADER,
)
from shared.utils.url_validation import UrlIssue

from market_scraper.main import app
from market_scraper.scraper_orchestrator.parse_product import (
    ParseProductError,
    ParseProductSuccess,
)
from market_scraper.infra.cache.conditional_payload import CachedResponseMetadata


def test_parse_route_returns_cached_304_when_request_is_not_modified(monkeypatch):
    metadata = CachedResponseMetadata(
        etag="etag-1",
        last_modified=datetime.now(timezone.utc).replace(microsecond=0),
        payload=ParserResponse(
            name="Produto",
            url="https://example.com/product",
            source="example.com",
        ),
    )

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_normalize_product_url",
        lambda url: "https://example.com/product",
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_check_url_compatibility",
        lambda url, ensure_public_endpoint=None: None,
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.get_cached_response",
        lambda url: metadata,
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.should_return_not_modified",
        lambda **kwargs: True,
    )

    client = TestClient(app)
    response = client.post(
        "/scraper/parse",
        json={"url": "example.com/product"},
        headers={"if-none-match": '"etag-1"'},
    )

    assert response.status_code == 304
    assert response.headers["etag"] == '"etag-1"'
    assert response.headers["x-marketscraper-cache-status"] == "hit"
    assert response.headers[SCRAPER_CONTRACT_VERSION_HEADER] == SCRAPER_CONTRACT_VERSION


def test_parse_route_returns_mapped_http_issue_and_invalidates_cache(monkeypatch):
    invalidated = []
    result = ParseProductError(
        kind="error",
        issue=UrlIssue(code="robots_disallowed", message="Bloqueado por robots.txt"),
        http_status=403,
        stage_timings={},
        invalidate_cache=True,
    )

    async def fake_execute(self, *args, **kwargs):
        return result

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_normalize_product_url",
        lambda url: "https://example.com/product",
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_check_url_compatibility",
        lambda url, ensure_public_endpoint=None: None,
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.get_cached_response",
        lambda url: None,
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product.ParseProduct.execute",
        fake_execute,
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.invalidate_cached_response",
        lambda url: invalidated.append(url),
    )

    client = TestClient(app)
    response = client.post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 403
    assert response.json()["error_code"] == "robots_disallowed"
    assert response.headers[SCRAPER_CONTRACT_VERSION_HEADER] == SCRAPER_CONTRACT_VERSION
    assert invalidated == ["https://example.com/product"]


def test_parse_route_returns_success_and_sets_cache_headers(monkeypatch):
    captured_kwargs: dict[str, object] = {}
    parser_response = ParserResponse(
        name="Produto",
        current_price=Decimal("12.34"),
        url="https://example.com/product",
        source="example.com",
        availability=True,
    )
    metadata = CachedResponseMetadata(
        etag="etag-2",
        last_modified=datetime.now(timezone.utc).replace(microsecond=0),
        payload=parser_response,
    )

    async def fake_execute(self, url, *, request_logger, force_refresh, trace_id):
        captured_kwargs["trace_id"] = trace_id
        return ParseProductSuccess(kind="success", parser_response=parser_response, stage_timings={})

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_normalize_product_url",
        lambda url: "https://example.com/product",
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_check_url_compatibility",
        lambda url, ensure_public_endpoint=None: None,
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.get_cached_response",
        lambda url: None,
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product.ParseProduct.execute",
        fake_execute,
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.store_response",
        lambda url, response: metadata,
    )

    client = TestClient(app)
    response = client.post(
        "/scraper/parse",
        json={
            "url": "example.com/product",
            "metadata": {
                "trace_id": "trace-from-alert",
                "correlation_id": "corr-123",
                "monitored_id": "mon-123",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Produto"
    assert response.headers["etag"] == '"etag-2"'
    assert response.headers["x-marketscraper-cache-status"] == "miss"
    assert response.headers[SCRAPER_CONTRACT_VERSION_HEADER] == SCRAPER_CONTRACT_VERSION
    assert captured_kwargs["trace_id"] == "trace-from-alert"


def test_parse_route_returns_invalid_url_error_when_compatibility_fails(monkeypatch):
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_normalize_product_url",
        lambda url: "https://blocked.example/product",
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_check_url_compatibility",
        lambda url, ensure_public_endpoint=None: UrlIssue(
            code="blocked_host",
            message="Host bloqueado",
        ),
    )

    client = TestClient(app)
    response = client.post("/scraper/parse", json={"url": "blocked.example/product"})

    assert response.status_code == 400
    assert response.json()["error_code"] == "blocked_host"
    assert response.headers[SCRAPER_CONTRACT_VERSION_HEADER] == SCRAPER_CONTRACT_VERSION


def test_parse_route_returns_429_for_anti_bot_page(monkeypatch):
    """Endpoint retorna 429 quando use case detecta página de anti-bot."""
    result = ParseProductError(
        kind="error",
        issue=UrlIssue(code="anti_bot_page", message="Página de proteção anti-bot detectada"),
        http_status=429,
        stage_timings={},
        invalidate_cache=True,
    )

    async def fake_execute(self, *args, **kwargs):
        return result

    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_normalize_product_url",
        lambda url: "https://example.com/product",
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.shared_check_url_compatibility",
        lambda url, ensure_public_endpoint=None: None,
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.get_cached_response",
        lambda url: None,
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product.ParseProduct.execute",
        fake_execute,
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.invalidate_cached_response",
        lambda url: None,
    )

    client = TestClient(app)
    response = client.post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 429
    assert response.json()["error_code"] == "anti_bot_page"
