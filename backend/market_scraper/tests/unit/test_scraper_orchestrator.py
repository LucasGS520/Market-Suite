"""Testes unitários para ScraperOrchestrator — fachada pública do orquestrador.

Valida que:
  - parse_product delega corretamente para ParseProduct.execute()
  - metadados de correlação são extraídos e propagados
  - health_check retorna estado OK
  - get_scraper_orchestrator() retorna instância válida
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
import structlog

from shared.schemas.shared_schemas_scraper import ParserResponse

from market_scraper.scraper_orchestrator.orchestrator import (
    ScraperOrchestrator,
    get_scraper_orchestrator,
)
from market_scraper.scraper_orchestrator.parse_product import (
    ParseProductError,
    ParseProductNoResult,
    ParseProductSuccess,
)
from shared.utils.url_validation import UrlIssue

_URL = "https://example.com/product"
_LOG = structlog.get_logger("test_scraper_orchestrator")


def _make_success() -> ParseProductSuccess:
    return ParseProductSuccess(
        kind="success",
        parser_response=ParserResponse(
            name="Produto",
            current_price=Decimal("99.90"),
            currency="BRL",
            availability=True,
            last_status="ok",
            url=_URL,
            source="example.com",
            payload={},
        ),
        stage_timings={"collect": 0.1, "extract": 0.05},
    )


def _make_no_result() -> ParseProductNoResult:
    return ParseProductNoResult(kind="no_result", reason_code="extraction_empty")


def _make_error() -> ParseProductError:
    return ParseProductError(
        kind="error",
        issue=UrlIssue(code="upstream_error", message="Falha"),
        http_status=503,
        stage_timings={},
    )


# ── Delegação para ParseProduct ───────────────────────────────────────────────

def test_orchestrator_delegates_to_parse_product_success(monkeypatch):
    expected = _make_success()

    async def fake_execute(self, url, *, request_logger, force_refresh, trace_id):
        return expected

    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.orchestrator.ParseProduct.execute",
        fake_execute,
    )

    result = asyncio.run(
        ScraperOrchestrator().parse_product(_URL, request_logger=_LOG)
    )

    assert result is expected
    assert isinstance(result, ParseProductSuccess)


def test_orchestrator_delegates_to_parse_product_no_result(monkeypatch):
    expected = _make_no_result()

    async def fake_execute(self, url, *, request_logger, force_refresh, trace_id):
        return expected

    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.orchestrator.ParseProduct.execute",
        fake_execute,
    )

    result = asyncio.run(ScraperOrchestrator().parse_product(_URL, request_logger=_LOG))

    assert isinstance(result, ParseProductNoResult)
    assert result.reason_code == "extraction_empty"


def test_orchestrator_delegates_to_parse_product_error(monkeypatch):
    expected = _make_error()

    async def fake_execute(self, url, *, request_logger, force_refresh, trace_id):
        return expected

    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.orchestrator.ParseProduct.execute",
        fake_execute,
    )

    result = asyncio.run(ScraperOrchestrator().parse_product(_URL, request_logger=_LOG))

    assert isinstance(result, ParseProductError)
    assert result.http_status == 503


# ── Propagação de metadados ───────────────────────────────────────────────────

def test_orchestrator_extracts_trace_id_from_metadata(monkeypatch):
    captured: dict = {}

    async def fake_execute(self, url, *, request_logger, force_refresh, trace_id):
        captured["trace_id"] = trace_id
        captured["force_refresh"] = force_refresh
        return _make_success()

    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.orchestrator.ParseProduct.execute",
        fake_execute,
    )

    asyncio.run(ScraperOrchestrator().parse_product(
        _URL,
        metadata={"trace_id": "abc-123", "force_refresh": True},
        request_logger=_LOG,
    ))

    assert captured["trace_id"] == "abc-123"
    assert captured["force_refresh"] is True


def test_orchestrator_explicit_trace_id_takes_priority(monkeypatch):
    captured: dict = {}

    async def fake_execute(self, url, *, request_logger, force_refresh, trace_id):
        captured["trace_id"] = trace_id
        return _make_success()

    monkeypatch.setattr(
        "market_scraper.scraper_orchestrator.orchestrator.ParseProduct.execute",
        fake_execute,
    )

    asyncio.run(ScraperOrchestrator().parse_product(
        _URL,
        metadata={"trace_id": "from-metadata"},
        trace_id="explicit-override",
        request_logger=_LOG,
    ))

    assert captured["trace_id"] == "explicit-override"


# ── health_check ──────────────────────────────────────────────────────────────

def test_orchestrator_health_check_returns_ok():
    result = asyncio.run(ScraperOrchestrator().health_check())
    assert result == {"orchestrator": "ok"}


# ── Factory ───────────────────────────────────────────────────────────────────

def test_get_scraper_orchestrator_returns_instance():
    orchestrator = get_scraper_orchestrator()
    assert isinstance(orchestrator, ScraperOrchestrator)


def test_get_scraper_orchestrator_returns_fresh_instance():
    a = get_scraper_orchestrator()
    b = get_scraper_orchestrator()
    assert a is not b
