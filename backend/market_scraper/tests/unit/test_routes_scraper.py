from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from shared.schemas import ParserResponse
from shared.utils.url_validation import UrlIssue

from market_scraper.main import app
from market_scraper.routes.response_helpers import _derive_no_result_reason
from market_scraper.services.synergic_pipeline import (
    PipelineContext,
    PipelineOutcome,
    StepExecution,
)
from market_scraper.utils.conditional_payload import CachedResponseMetadata


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


def test_parse_route_returns_mapped_http_issue_and_invalidates_cache(monkeypatch):
    invalidated = []
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )
    outcome = PipelineOutcome(
        status="error",
        context=context,
        steps=[
            StepExecution(
                name="fetch_html",
                status="error",
                duration_seconds=0.1,
                message="unsupported_by_robots",
            )
        ],
    )

    async def fake_run_pipeline(*args, **kwargs):
        return outcome

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
        "market_scraper.routes.routes_scraper.run_pipeline",
        fake_run_pipeline,
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.invalidate_cached_response",
        lambda url: invalidated.append(url),
    )

    client = TestClient(app)
    response = client.post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 403
    assert response.json()["error_code"] == "unsupported_by_robots"
    assert invalidated == ["https://example.com/product"]


def test_parse_route_returns_success_and_sets_cache_headers(monkeypatch):
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )
    outcome = PipelineOutcome(
        status="success",
        context=context,
        payload={
            "name": "Produto",
            "current_price": "12.34",
            "url": "https://example.com/product",
            "source": "example.com",
            "availability": True,
        },
    )
    metadata = CachedResponseMetadata(
        etag="etag-2",
        last_modified=datetime.now(timezone.utc).replace(microsecond=0),
        payload=ParserResponse(
            name="Produto",
            current_price=Decimal("12.34"),
            url="https://example.com/product",
            source="example.com",
        ),
    )

    async def fake_run_pipeline(*args, **kwargs):
        return outcome

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
        "market_scraper.routes.routes_scraper.run_pipeline",
        fake_run_pipeline,
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.parse_price_str",
        lambda value, url: Decimal("12.34"),
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.store_response",
        lambda url, response: metadata,
    )

    client = TestClient(app)
    response = client.post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 200
    assert response.json()["name"] == "Produto"
    assert response.headers["etag"] == '"etag-2"'
    assert response.headers["x-marketscraper-cache-status"] == "miss"


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


# ──────────────────────────────────────────────────────────────────────────────
# Fase 2 — testes de regressão: reason_code derivado em build_no_result_response
# ──────────────────────────────────────────────────────────────────────────────


def _make_context(*, html: str | None = None, data: dict | None = None) -> PipelineContext:
    ctx = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )
    ctx.html = html
    if data:
        ctx.data.update(data)
    return ctx


def test_derive_no_result_reason_html_unavailable():
    """reason_code é html_unavailable quando HTML está ausente."""
    outcome = PipelineOutcome(
        status="empty",
        context=_make_context(html=None),
    )
    assert _derive_no_result_reason(outcome) == "html_unavailable"


def test_derive_no_result_reason_no_domain_parser():
    """reason_code é no_domain_parser quando domínio não tem parser dedicado."""
    outcome = PipelineOutcome(
        status="empty",
        context=_make_context(
            html="<html><body>conteúdo</body></html>",
            data={"no_domain_parser": True},
        ),
    )
    assert _derive_no_result_reason(outcome) == "no_domain_parser"


def test_derive_no_result_reason_no_parser_data():
    """reason_code é no_parser_data quando HTML está presente mas nenhum parser extraiu dados."""
    outcome = PipelineOutcome(
        status="empty",
        context=_make_context(html="<html><body>conteúdo sem preço</body></html>"),
    )
    assert _derive_no_result_reason(outcome) == "no_parser_data"


def test_parse_route_returns_429_for_anti_bot_page(monkeypatch):
    """Endpoint retorna 429 quando pipeline detecta página de anti-bot."""
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )
    outcome = PipelineOutcome(
        status="error",
        context=context,
        steps=[
            StepExecution(
                name="anti_bot_detection",
                status="error",
                duration_seconds=0.0,
                message="anti_bot_page",
            )
        ],
    )

    async def fake_run_pipeline(*args, **kwargs):
        return outcome

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
        "market_scraper.routes.routes_scraper.run_pipeline",
        fake_run_pipeline,
    )
    monkeypatch.setattr(
        "market_scraper.routes.routes_scraper.invalidate_cached_response",
        lambda url: None,
    )

    client = TestClient(app)
    response = client.post("/scraper/parse", json={"url": "example.com/product"})

    assert response.status_code == 429
    assert response.json()["error_code"] == "anti_bot_page"
