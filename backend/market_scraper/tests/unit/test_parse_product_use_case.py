"""Testes unitários de ParseProductUseCase.

Cobre os 4 cenários de saída (success, timeout, http_issue, no_result)
e verifica que stage_timings está preenchido em todos os casos.
Não testa I/O real — run_pipeline é sempre monkeypatched.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog

from shared.schemas.shared_schemas_scraper import ParserResponse

from market_scraper.services.synergic_pipeline import (
    PipelineContext,
    PipelineOutcome,
    PipelineTimeoutError,
    StepExecution,
)
from market_scraper.use_cases.parse_product import (
    ParseProductError,
    ParseProductNoResult,
    ParseProductSuccess,
    ParseProductUseCase,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _logger() -> MagicMock:
    spy = MagicMock()
    spy.warning = MagicMock()
    spy.info = MagicMock()
    return spy


def _ctx() -> PipelineContext:
    return PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )


def _success_outcome(payload: dict) -> PipelineOutcome:
    return PipelineOutcome(status="success", context=_ctx(), payload=payload)


def _error_outcome(step_message: str) -> PipelineOutcome:
    return PipelineOutcome(
        status="error",
        context=_ctx(),
        steps=[StepExecution(name="fetch", status="error", duration_seconds=0.0, message=step_message)],
    )


# ── Cenário: sucesso ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_returns_success_with_valid_payload(monkeypatch):
    outcome = _success_outcome({"name": "Produto", "current_price": "99.90"})
    monkeypatch.setattr(
        "market_scraper.use_cases.parse_product.run_pipeline",
        AsyncMock(return_value=outcome),
    )

    result = await ParseProductUseCase().execute(
        "https://example.com/product",
        request_logger=_logger(),
        trace_id="trace-1",
    )

    assert isinstance(result, ParseProductSuccess)
    assert result.kind == "success"
    assert isinstance(result.parser_response, ParserResponse)
    assert result.parser_response.name == "Produto"
    assert result.parser_response.current_price == Decimal("99.90")


@pytest.mark.asyncio
async def test_execute_success_fills_all_stage_timings(monkeypatch):
    outcome = _success_outcome({"name": "Produto", "current_price": "10.00"})
    monkeypatch.setattr(
        "market_scraper.use_cases.parse_product.run_pipeline",
        AsyncMock(return_value=outcome),
    )

    result = await ParseProductUseCase().execute(
        "https://example.com/product",
        request_logger=_logger(),
    )

    assert isinstance(result, ParseProductSuccess)
    for stage in ("collect", "extract", "post_process", "build_response"):
        assert stage in result.stage_timings
        assert result.stage_timings[stage] >= 0.0


# ── Cenário: timeout ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_returns_error_on_pipeline_timeout(monkeypatch):
    async def _raise(*args, **kwargs):
        raise PipelineTimeoutError("timeout")

    monkeypatch.setattr("market_scraper.use_cases.parse_product.run_pipeline", _raise)

    result = await ParseProductUseCase().execute(
        "https://example.com/product",
        request_logger=_logger(),
    )

    assert isinstance(result, ParseProductError)
    assert result.kind == "error"
    assert result.http_status == 504
    assert result.issue.code == "pipeline_timeout"
    assert result.invalidate_cache is False
    assert "collect" in result.stage_timings


# ── Cenário: falha de aquisição HTTP (extract blocked) ───────────────────────

@pytest.mark.asyncio
async def test_execute_returns_error_for_anti_bot_page(monkeypatch):
    outcome = _error_outcome("anti_bot_page")
    monkeypatch.setattr(
        "market_scraper.use_cases.parse_product.run_pipeline",
        AsyncMock(return_value=outcome),
    )

    result = await ParseProductUseCase().execute(
        "https://example.com/product",
        request_logger=_logger(),
    )

    assert isinstance(result, ParseProductError)
    assert result.http_status == 429
    assert result.issue.code == "anti_bot_page"
    assert result.invalidate_cache is True
    assert "extract" in result.stage_timings


@pytest.mark.asyncio
async def test_execute_returns_error_for_unsupported_by_robots(monkeypatch):
    outcome = _error_outcome("unsupported_by_robots")
    monkeypatch.setattr(
        "market_scraper.use_cases.parse_product.run_pipeline",
        AsyncMock(return_value=outcome),
    )

    result = await ParseProductUseCase().execute(
        "https://example.com/product",
        request_logger=_logger(),
    )

    assert isinstance(result, ParseProductError)
    assert result.http_status == 403
    assert result.issue.code == "unsupported_by_robots"
    assert result.invalidate_cache is True


@pytest.mark.asyncio
async def test_execute_returns_error_for_playwright_not_ready(monkeypatch):
    outcome = _error_outcome("playwright_not_ready")
    monkeypatch.setattr(
        "market_scraper.use_cases.parse_product.run_pipeline",
        AsyncMock(return_value=outcome),
    )

    result = await ParseProductUseCase().execute(
        "https://example.com/product",
        request_logger=_logger(),
    )

    assert isinstance(result, ParseProductError)
    assert result.http_status == 503
    assert result.issue.code == "pipeline_degraded"
    assert result.invalidate_cache is True


# ── Cenário: no_result ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_returns_no_result_when_pipeline_status_is_not_success(monkeypatch):
    ctx = _ctx()
    outcome = PipelineOutcome(status="no_result", context=ctx)
    monkeypatch.setattr(
        "market_scraper.use_cases.parse_product.run_pipeline",
        AsyncMock(return_value=outcome),
    )

    result = await ParseProductUseCase().execute(
        "https://example.com/product",
        request_logger=_logger(),
    )

    assert isinstance(result, ParseProductNoResult)
    assert result.kind == "no_result"
    assert result.outcome is outcome
    assert "post_process" in result.stage_timings


@pytest.mark.asyncio
async def test_execute_returns_no_result_when_payload_lacks_useful_data(monkeypatch):
    outcome = _success_outcome({"name": "Produto"})  # sem current_price → not useful
    monkeypatch.setattr(
        "market_scraper.use_cases.parse_product.run_pipeline",
        AsyncMock(return_value=outcome),
    )

    result = await ParseProductUseCase().execute(
        "https://example.com/product",
        request_logger=_logger(),
    )

    assert isinstance(result, ParseProductNoResult)


@pytest.mark.asyncio
async def test_execute_returns_success_when_availability_is_false_without_price(monkeypatch):
    outcome = _success_outcome({"availability": False})
    monkeypatch.setattr(
        "market_scraper.use_cases.parse_product.run_pipeline",
        AsyncMock(return_value=outcome),
    )

    result = await ParseProductUseCase().execute(
        "https://example.com/product",
        request_logger=_logger(),
    )

    assert isinstance(result, ParseProductSuccess)
    assert result.parser_response.availability is False


# ── Feature flag na rota ──────────────────────────────────────────────────────

def test_route_new_orchestrator_flag_produces_same_response_as_legacy(monkeypatch):
    """Ambos os caminhos (flag True/False) devem retornar resposta 200 idêntica."""
    from fastapi.testclient import TestClient
    from market_scraper.main import app
    from market_scraper.core.config_scraper import settings as scraper_settings

    ctx = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )
    outcome = PipelineOutcome(
        status="success",
        context=ctx,
        payload={"name": "Produto Flag Test", "current_price": "55.00", "availability": True},
    )

    async def fake_pipeline(url, *, force_refresh=False, trace_id=None):
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
        "market_scraper.routes.routes_scraper.store_response",
        lambda url, response: None,
    )
    monkeypatch.setattr("market_scraper.routes.routes_scraper.run_pipeline", fake_pipeline)
    monkeypatch.setattr("market_scraper.use_cases.parse_product.run_pipeline", fake_pipeline)

    client = TestClient(app)

    # Caminho legado (flag=False)
    monkeypatch.setattr(scraper_settings, "SCRAPER_NEW_ORCHESTRATOR_ENABLED", False)
    resp_legacy = client.post("/scraper/parse", json={"url": "example.com/product"})

    # Caminho novo (flag=True)
    monkeypatch.setattr(scraper_settings, "SCRAPER_NEW_ORCHESTRATOR_ENABLED", True)
    resp_new = client.post("/scraper/parse", json={"url": "example.com/product"})

    assert resp_legacy.status_code == 200
    assert resp_new.status_code == 200
    assert resp_legacy.json()["name"] == resp_new.json()["name"]
    assert resp_legacy.json()["current_price"] == resp_new.json()["current_price"]
