from __future__ import annotations

import httpx

from market_scraper.services.pipeline_steps import (
    DomainSpecificParserStep,
    FetchHTMLStep,
)
from market_scraper.services.synergic_pipeline import PipelineContext


async def test_fetch_html_step_returns_failure_when_robots_disallow(monkeypatch):
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )

    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        assert url == context.url
        assert timeout == 1.0
        return False

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )

    step = FetchHTMLStep()
    result = await step.run(context)

    assert result.status == "error"
    assert result.message == "unsupported_by_robots"


async def test_fetch_html_step_reuses_cached_html(monkeypatch):
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )

    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.cache.get",
        lambda url: "<html>cached</html>",
    )

    async def fail_coalesce(key, producer):
        raise AssertionError("singleflight nao deveria ser usado com cache hit")

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.singleflight.coalesce_with_leader",
        fail_coalesce,
    )

    step = FetchHTMLStep()
    result = await step.run(context)

    assert result.status == "success"
    assert result.message == "html_from_cache"
    assert context.html == "<html>cached</html>"


async def test_fetch_html_step_infers_unavailability_from_http_status(monkeypatch):
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )
    request = httpx.Request("GET", context.url)
    response = httpx.Response(404, request=request)

    async def fake_is_allowed(url: str, *, timeout: float) -> bool:
        return True

    async def fake_coalesce(key, producer):
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    class _Inference:
        availability = False
        last_status = "not_found"
        confidence = "high"

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.robots.is_allowed",
        fake_is_allowed,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.singleflight.coalesce_with_leader",
        fake_coalesce,
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.infer_availability_from_http_status",
        lambda status_code, domain: _Inference(),
    )

    step = FetchHTMLStep()
    result = await step.run(context)

    assert result.status == "success"
    assert result.payload == {
        "name": None,
        "current_price": None,
        "url": context.url,
        "source": context.source,
        "availability": False,
        "last_status": "not_found",
    }
    assert context.html == ""
    assert context.data["http_status"] == 404
    assert context.data["availability"] is False
    assert context.data["last_status"] == "not_found"


async def test_domain_specific_parser_step_uses_dedicated_parser(monkeypatch):
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
        html="<html>ok</html>",
    )

    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.get_domain_parser",
        lambda domain: ("example", lambda html, url: {"name": "Produto"}),
    )
    monkeypatch.setattr(
        "market_scraper.services.pipeline_steps.run_parser_with_validation",
        lambda **kwargs: (
            True,
            {
                "name": "Produto",
                "current_price": "10.00",
                "url": context.url,
                "source": context.source,
            },
        ),
    )

    step = DomainSpecificParserStep()
    result = await step.run(context)

    assert result.status == "success"
    assert result.payload is not None
    assert context.data["domain_parser_suffix"] == "example"
