"""Testes unitários para ParseProduct — fluxo canônico de orquestração.

Valida:
  - ordem de estágios: robots → rate_limiter → collect → extract → post_process → response
  - mapeamento de erros de coleta → ParseProductError com HTTP correto
  - produto indisponível (404) → ParseProductSuccess com availability=False
  - extração vazia → ParseProductNoResult
  - robots bloqueado → ParseProductError 403
  - stage_timings presentes em todos os cenários de sucesso
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal

import pytest
import structlog

from shared.schemas.shared_schemas_scraper import ParserResponse

from market_scraper.collection.dto.collected_document import CollectedDocument
from market_scraper.collection.dto.collection_attempt import CollectionAttempt
from market_scraper.domain.dtos import ParseAttempt, ParseResult, PostProcessResult
from market_scraper.scraper_orchestrator.parse_product import (
    ParseProduct,
    ParseProductError,
    ParseProductNoResult,
    ParseProductSuccess,
)

_URL = "https://example.com/product"
_DOMAIN = "example.com"
_LOG = structlog.get_logger("test_parse_product")


# ── Factories de fixtures ─────────────────────────────────────────────────────

def _make_doc(
    *,
    html: str | None = "<html><body>produto</body></html>",
    http_status: int | None = 200,
    layer_used: str = "http",
    fallback_taken: bool = False,
    anti_bot_detected: bool = False,
    anti_bot_pattern: str | None = None,
    error_code: str | None = None,
    classification_reason: str | None = "html_valid",
    anti_bot_bypassed: bool = False,
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
        duration_ms=50.0,
        attempts=(CollectionAttempt(layer="http", status="success", error_code=None, duration_ms=50.0, reason=None),),
        error_code=error_code,
        classification_reason=classification_reason,
        anti_bot_bypassed=anti_bot_bypassed,
    )


def _make_parse_result(*, payload=None) -> ParseResult:
    p = payload if payload is not None else {"name": "Produto X", "current_price": "199.90", "url": _URL}
    return ParseResult(
        payload=p,
        attempts=(ParseAttempt(parser_name="parsel", step_name="parsel", succeeded=True),),
    )


def _make_post_result(*, available: bool = True) -> PostProcessResult:
    return PostProcessResult(
        name="Produto X",
        current_price=Decimal("199.90"),
        currency="BRL",
        availability=available,
        last_status="ok",
        url=_URL,
        source=_DOMAIN,
    )


def _fake_parser_response(post_result: PostProcessResult, *, request_logger) -> ParserResponse:
    return ParserResponse(
        name=post_result.name,
        current_price=post_result.current_price,
        currency=post_result.currency,
        availability=post_result.availability,
        last_status=post_result.last_status,
        url=post_result.url,
        source=post_result.source,
        payload={},
    )


def _patch_full_flow(monkeypatch, *, doc: CollectedDocument | None = None, post_result: PostProcessResult | None = None):
    """Aplica stubs para o caminho feliz completo."""
    _doc = doc or _make_doc()
    _post = post_result or _make_post_result()

    async def fake_is_allowed(url, timeout):
        return True

    async def fake_should_allow(domain):
        return True, None

    async def fake_coalesce(key, producer):
        return await producer(), True

    class StubRuntime:
        async def fetch_with_fallback(self, url, *, domain, http_timeout, browser_timeout):
            return _doc

    class StubChain:
        def run(self, html, url, source, *, http_status=None):
            return _make_parse_result()

    class StubProcessor:
        def run(self, payload, acquisition, url, source):
            return _post

    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product._robots.is_allowed", fake_is_allowed)
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.adaptive_rate_limiter.should_allow", fake_should_allow)
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.get_crawlee_runtime", lambda: StubRuntime())
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.singleflight.coalesce_with_leader", fake_coalesce)
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.get_extraction_chain", lambda: StubChain())
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.get_post_processor", lambda: StubProcessor())
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product.build_parser_response",
        _fake_parser_response,
    )


# ── Fluxo de sucesso canônico ─────────────────────────────────────────────────

def test_parse_product_executes_canonical_stage_order(monkeypatch):
    calls: list[str] = []

    async def fake_is_allowed(url, timeout):
        calls.append("robots")
        return True

    async def fake_should_allow(domain):
        calls.append("rate_limiter")
        return True, None

    async def fake_coalesce(key, producer):
        result = await producer()
        calls.append("collect")
        return result, True

    class StubRuntime:
        async def fetch_with_fallback(self, url, *, domain, http_timeout, browser_timeout):
            return _make_doc()

    class StubChain:
        def run(self, html, url, source, *, http_status=None):
            calls.append("extract")
            return _make_parse_result()

    class StubProcessor:
        def run(self, payload, acquisition, url, source):
            calls.append("post_process")
            return _make_post_result()

    def fake_build_response(post_result, *, request_logger):
        calls.append("build_response")
        return _fake_parser_response(post_result, request_logger=request_logger)

    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product._robots.is_allowed", fake_is_allowed)
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.adaptive_rate_limiter.should_allow", fake_should_allow)
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.get_crawlee_runtime", lambda: StubRuntime())
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.singleflight.coalesce_with_leader", fake_coalesce)
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.get_extraction_chain", lambda: StubChain())
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.get_post_processor", lambda: StubProcessor())
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.build_parser_response", fake_build_response)

    result = asyncio.run(ParseProduct().execute(_URL, request_logger=_LOG))

    assert isinstance(result, ParseProductSuccess)
    assert calls == ["robots", "rate_limiter", "collect", "extract", "post_process", "build_response"]
    assert result.parser_response.name == "Produto X"


def test_parse_product_acquisition_telemetry_from_collected_document(monkeypatch):
    captured: dict = {}

    class StubProcessor:
        def run(self, payload, acquisition, url, source):
            captured["acquisition"] = acquisition
            return _make_post_result()

    _patch_full_flow(monkeypatch, doc=_make_doc(
        layer_used="browser",
        fallback_taken=True,
        anti_bot_detected=True,
        classification_reason="anti_bot",
        anti_bot_bypassed=False,
    ))
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.get_post_processor", lambda: StubProcessor())

    asyncio.run(ParseProduct().execute(_URL, request_logger=_LOG))

    acq = captured["acquisition"]
    assert acq.layer_used == "browser"
    assert acq.fallback_taken is True
    assert acq.anti_bot_detected is True
    assert acq.classification_reason == "anti_bot"
    assert acq.anti_bot_bypassed is False


def test_parse_product_emits_canonical_telemetry(monkeypatch):
    events: list[tuple[str, dict]] = []

    class RecordingTelemetryService:
        def __init__(self, *, trace_id, domain):
            events.append(("init", {"trace_id": trace_id, "domain": domain}))

        def collection_started(self, **kwargs):
            events.append(("collection_started", kwargs))

        def collection_completed(self, **kwargs):
            events.append(("collection_completed", kwargs))

        def extraction_started(self):
            events.append(("extraction_started", {}))

        def extraction_completed(self, **kwargs):
            events.append(("extraction_completed", kwargs))

        def post_processing_started(self):
            events.append(("post_processing_started", {}))

        def post_processing_completed(self, **kwargs):
            events.append(("post_processing_completed", kwargs))

        def pipeline_completed(self, **kwargs):
            events.append(("pipeline_completed", kwargs))

    _patch_full_flow(
        monkeypatch,
        doc=_make_doc(
            layer_used="browser",
            fallback_taken=True,
            anti_bot_detected=True,
            http_status=200,
        ),
    )
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product.TelemetryService",
        RecordingTelemetryService,
    )

    result = asyncio.run(ParseProduct().execute(_URL, request_logger=_LOG, trace_id="trace-1"))

    assert isinstance(result, ParseProductSuccess)
    assert [event for event, _ in events] == [
        "init",
        "collection_started",
        "collection_completed",
        "extraction_started",
        "extraction_completed",
        "post_processing_started",
        "post_processing_completed",
        "pipeline_completed",
    ]
    assert events[0][1] == {"trace_id": "trace-1", "domain": _DOMAIN}
    assert events[2][1]["layer"] == "browser"
    assert events[2][1]["fallback_taken"] is True
    assert events[-1][1]["outcome"] == "success"


# ── Produto indisponível (404/410/451) ────────────────────────────────────────

@pytest.mark.parametrize("status_code", [404, 410, 451])
def test_parse_product_handles_unavailable_http_status(monkeypatch, status_code):
    unavailable_doc = _make_doc(
        html=None,
        http_status=status_code,
        error_code=f"http_{status_code}_unavailable",
        classification_reason=f"http_{status_code}_unavailable",
    )

    async def fake_is_allowed(url, timeout):
        return True

    async def fake_should_allow(domain):
        return True, None

    async def fake_coalesce(key, producer):
        return await producer(), True

    class StubRuntime:
        async def fetch_with_fallback(self, url, *, domain, http_timeout, browser_timeout):
            return unavailable_doc

    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product._robots.is_allowed", fake_is_allowed)
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.adaptive_rate_limiter.should_allow", fake_should_allow)
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.get_crawlee_runtime", lambda: StubRuntime())
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.singleflight.coalesce_with_leader", fake_coalesce)
    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.parse_product.build_parser_response",
        _fake_parser_response,
    )

    result = asyncio.run(ParseProduct().execute(_URL, request_logger=_LOG))

    assert isinstance(result, ParseProductSuccess)
    assert result.parser_response.availability is False


# ── Extração vazia → NoResult ─────────────────────────────────────────────────

def test_parse_product_returns_no_result_when_extraction_empty(monkeypatch):
    class StubChain:
        def run(self, html, url, source, *, http_status=None):
            return _make_parse_result(payload=None)

    class StubProcessor:
        def run(self, payload, acquisition, url, source):
            return PostProcessResult(
                name=None, current_price=None, currency=None,
                availability=None, last_status=None,
                url=url, source=source or "",
            )

    _patch_full_flow(monkeypatch)
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.get_extraction_chain", lambda: StubChain())
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.get_post_processor", lambda: StubProcessor())

    result = asyncio.run(ParseProduct().execute(_URL, request_logger=_LOG))

    assert isinstance(result, ParseProductNoResult)
    assert result.reason_code == "extraction_empty"


# ── Erros de coleta → ParseProductError ──────────────────────────────────────

@pytest.mark.parametrize("error_code,expected_http", [
    ("anti_bot_page", 429),
    ("rate_limiter_cooldown", 429),
    ("too_many_redirects", 422),
    ("invalid_url", 422),
    ("playwright_timeout", 504),
    ("playwright_fetch_error", 503),
    ("playwright_not_ready", 503),
    ("pipeline_degraded", 503),
    ("upstream_error", 503),
])
def test_parse_product_maps_collection_errors(monkeypatch, error_code, expected_http):
    async def fake_is_allowed(url, timeout):
        return True

    async def fake_should_allow(domain):
        return True, None

    async def fake_coalesce(key, producer):
        return await producer(), True

    error_doc = _make_doc(html=None, http_status=None, error_code=error_code)

    class StubRuntime:
        async def fetch_with_fallback(self, url, *, domain, http_timeout, browser_timeout):
            return error_doc

    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product._robots.is_allowed", fake_is_allowed)
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.adaptive_rate_limiter.should_allow", fake_should_allow)
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.get_crawlee_runtime", lambda: StubRuntime())
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.singleflight.coalesce_with_leader", fake_coalesce)

    result = asyncio.run(ParseProduct().execute(_URL, request_logger=_LOG))

    assert isinstance(result, ParseProductError)
    assert result.http_status == expected_http


# ── Robots bloqueado ──────────────────────────────────────────────────────────

def test_parse_product_robots_block(monkeypatch):
    async def fake_is_allowed(url, timeout):
        return False

    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product._robots.is_allowed", fake_is_allowed)
    monkeypatch.setattr("market_scraper.scraper_orchestrator.parse_product.settings.SCRAPER_ROBOTS_MODE", "block")

    result = asyncio.run(ParseProduct().execute(_URL, request_logger=_LOG))

    assert isinstance(result, ParseProductError)
    assert result.http_status == 403
    assert result.issue.code == "unsupported_by_robots"


# ── Stage timings ─────────────────────────────────────────────────────────────

def test_parse_product_stage_timings_populated(monkeypatch):
    _patch_full_flow(monkeypatch)

    result = asyncio.run(ParseProduct().execute(_URL, request_logger=_LOG))

    assert isinstance(result, ParseProductSuccess)
    for stage in ("collect", "extract", "post_process", "build_response"):
        assert stage in result.stage_timings
        assert result.stage_timings[stage] >= 0
