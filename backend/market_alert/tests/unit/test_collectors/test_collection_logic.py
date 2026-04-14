""" Testes unitarios para fluxo auxiliar de coleta compartilhada. """

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shared.schemas import ParserResponse
from shared.schemas.shared_schemas_scraper import ScrapeResult

from market_alert.collectors.services import scraper_common
from market_alert.collectors.utils.collector_result import (
    _resolve_no_result_reason,
    _should_schedule_temporary_retry,
)

import market_alert.collectors.tasks.collector_product_task as collector_task_module


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers de mock para testes de collect_product
# ---------------------------------------------------------------------------

class _FakeDB(SimpleNamespace):
    """Stub de Session para testes que não atingem banco."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _make_monitored_payload(**overrides) -> dict:
    from uuid import uuid4
    payload = {
        "version": 1,
        "kind": "monitored",
        "monitored_id": str(uuid4()),
        "url": "https://store.example.com/produto",
        "trace_id": str(uuid4()),
        "user_id": str(uuid4()),
        "name": "Produto Teste",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# error_category — classificação de desfecho na collect_product
# ---------------------------------------------------------------------------

def test_collect_product_error_category_operational_on_lock_skipped(monkeypatch) -> None:
    """lock_skipped deve ser classificado como operational (ruído de concorrência)."""
    captured_logs: list[dict] = []

    monkeypatch.setattr(collector_task_module, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(collector_task_module, "acquire_product_lock", lambda target, ttl_seconds=None: (False, None))

    class _LogBound:
        def bind(self, **kwargs):
            return self
        def info(self, event, **kwargs):
            captured_logs.append({"event": event, **kwargs})
        def warning(self, event, **kwargs):
            captured_logs.append({"event": event, **kwargs})
        def error(self, event, **kwargs):
            captured_logs.append({"event": event, **kwargs})
        def exception(self, event, **kwargs):
            captured_logs.append({"event": event, **kwargs})

    payload = _make_monitored_payload()
    db = _FakeDB()

    outcome, result, reason = collector_task_module.collect_product(
        payload,
        use_lock=True,
        dispatch_comparison=False,
        logger_bound=_LogBound(),
        db=db,
    )

    assert reason == "lock_skipped"
    finished_log = next(
        (e for e in captured_logs if e["event"] == "collect_product_finished"), None
    )
    assert finished_log is not None
    assert finished_log["error_category"] == "operational"
    assert finished_log["semantic_category"] == "neutral"
    assert finished_log["source_integrity"] is False


def test_collect_product_error_category_none_on_success(monkeypatch) -> None:
    """Coleta bem-sucedida deve ter error_category='none'."""
    captured_logs: list[dict] = []
    captured_request_metadata: dict[str, object] = {}

    from uuid import UUID, uuid4
    from decimal import Decimal as D

    monitored_id_str = str(uuid4())
    user_id_str = str(uuid4())

    class _LogBound:
        def bind(self, **kwargs):
            return self
        def info(self, event, **kwargs):
            captured_logs.append({"event": event, **kwargs})
        def warning(self, event, **kwargs):
            captured_logs.append({"event": event, **kwargs})
        def error(self, event, **kwargs):
            captured_logs.append({"event": event, **kwargs})
        def exception(self, event, **kwargs):
            captured_logs.append({"event": event, **kwargs})

    success_result = ScrapeResult(
        status="success",
        product_id=monitored_id_str,
        http_status=200,
        price_changed=True,
    )

    monkeypatch.setattr(collector_task_module, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(collector_task_module, "acquire_product_lock", lambda target, ttl_seconds=None: (True, "lock-owner"))
    monkeypatch.setattr(collector_task_module, "release_product_lock", lambda target, owner: True)
    monkeypatch.setattr(
        collector_task_module,
        "scrape_monitored_product",
        lambda db, url, user_id, payload, collected_at, request_metadata=None: (
            captured_request_metadata.update(request_metadata or {}) or success_result
        ),
    )
    monkeypatch.setattr(
        collector_task_module,
        "get_monitored_product_by_id",
        lambda db, mid: SimpleNamespace(id=UUID(monitored_id_str), user_id=UUID(user_id_str), paused=False),
    )
    monkeypatch.setattr(collector_task_module, "activate_pending_monitored", lambda db, mid, commit=True: None)
    monkeypatch.setattr(collector_task_module, "schedule_comparison_after_commit", lambda *a, **kw: None)

    payload = _make_monitored_payload(
        monitored_id=monitored_id_str,
        user_id=user_id_str,
        correlation_id="corr-collect-1",
    )
    db = _FakeDB()

    outcome, result, reason = collector_task_module.collect_product(
        payload,
        use_lock=True,
        dispatch_comparison=True,
        logger_bound=_LogBound(),
        db=db,
    )

    assert outcome == "success"
    finished_log = next(
        (e for e in captured_logs if e["event"] == "collect_product_finished"), None
    )
    assert finished_log is not None
    assert finished_log["error_category"] == "none"
    assert finished_log["semantic_category"] is None
    assert finished_log["source_integrity"] is True
    assert finished_log["correlation_id"] == "corr-collect-1"
    assert captured_request_metadata == {
        "trace_id": payload["trace_id"],
        "correlation_id": "corr-collect-1",
        "monitored_id": monitored_id_str,
        "competitor_id": None,
    }


def test_collect_product_error_category_operational_on_invalid_payload(monkeypatch) -> None:
    """Payload inválido deve retornar error_category='domain'."""
    captured_logs: list[dict] = []

    class _LogBound:
        def bind(self, **kwargs):
            return self
        def info(self, event, **kwargs):
            captured_logs.append({"event": event, **kwargs})
        def warning(self, event, **kwargs):
            captured_logs.append({"event": event, **kwargs})
        def error(self, event, **kwargs):
            captured_logs.append({"event": event, **kwargs})
        def exception(self, event, **kwargs):
            captured_logs.append({"event": event, **kwargs})

    db = _FakeDB()

    # Payload None → invalid_payload reason
    outcome, result, reason = collector_task_module.collect_product(
        None,
        use_lock=False,
        dispatch_comparison=False,
        logger_bound=_LogBound(),
        db=db,
    )

    assert reason == "invalid_payload"
    finished_log = next(
        (e for e in captured_logs if e["event"] == "collect_product_finished"), None
    )
    assert finished_log is not None
    # invalid_payload está em _DOMAIN_REASONS
    assert finished_log["error_category"] == "domain"
    assert finished_log["semantic_category"] == "structural"
    assert finished_log["source_integrity"] is False


def test_execute_scraper_fetch_prefers_mocked_parse() -> None:
    parse_mock = Mock(
        return_value=ParserResponse(
            name="Produto",
            current_price=Decimal("99.90"),
            currency="BRL",
        )
    )
    client = SimpleNamespace(parse=parse_mock, fetch=Mock())

    result = scraper_common.execute_scraper_fetch(
        client,
        url="https://example.com/produto",
        product_type="monitored",
        monitored_id="id-1",
        user_id=None,
        metadata={"trace_id": "trace-1"},
        etag="etag-1",
        last_modified=datetime(2026, 4, 7, 10, 0, 0, tzinfo=timezone.utc),
        force_refresh=False,
    )

    assert result.status_code == 200
    assert result.payload.name == "Produto"
    client.fetch.assert_not_called()


def test_execute_scraper_fetch_uses_client_fetch_when_parse_is_not_mocked() -> None:
    client = SimpleNamespace(
        parse=lambda **kwargs: None,
        fetch=Mock(return_value=SimpleNamespace(status_code=304, payload=None, headers={})),
    )

    result = scraper_common.execute_scraper_fetch(
        client,
        url="https://example.com/produto",
        product_type="competitor",
        monitored_id=None,
        user_id=None,
        metadata=None,
        etag=None,
        last_modified=None,
        force_refresh=True,
    )

    assert result.status_code == 304
    client.fetch.assert_called_once()


def test_resolve_availability_prioritizes_price_presence() -> None:
    assert scraper_common.resolve_availability(Decimal("10.00"), False) is True


def test_resolve_availability_returns_false_for_explicit_unavailable_without_price() -> None:
    assert scraper_common.resolve_availability(None, False) is False


# ──────────────────────────────────────────────────────────────────────────────
# Fase 3 — testes de regressão: contrato de retorno da coleta de concorrentes
# ──────────────────────────────────────────────────────────────────────────────


def test_resolve_no_result_reason_lock_skipped() -> None:
    """lock_skipped deve retornar razão explícita, não genérica 'validation'."""
    result = ScrapeResult(status="no_result", error_code="lock_skipped", product_id="id-1", http_status=200)
    assert _resolve_no_result_reason(result) == "lock_skipped"


def test_resolve_no_result_reason_paused() -> None:
    """Concorrente pausado deve retornar razão 'paused', não 'validation'."""
    result = ScrapeResult(status="no_result", error_code="paused", product_id="id-1", http_status=200)
    assert _resolve_no_result_reason(result) == "paused"


def test_resolve_no_result_reason_missing_target() -> None:
    """Alvo inexistente deve retornar razão 'missing_target', não 'validation'."""
    result = ScrapeResult(status="no_result", error_code="missing_target", product_id="id-1", http_status=404)
    assert _resolve_no_result_reason(result) == "missing_target"


def test_resolve_no_result_reason_no_result_falls_to_parse_empty() -> None:
    """Scraper retornando no_result legítimo deve usar o catálogo domain_empty."""
    result = ScrapeResult(status="no_result", error_code="no_result", product_id="id-1", http_status=422)
    assert _resolve_no_result_reason(result) == "parse_empty"


def test_resolve_no_result_reason_rate_limit_maps_to_http_429() -> None:
    """Rate limit deve usar o reason tipado do catálogo compartilhado."""
    result = ScrapeResult(status="no_result", error_code="rate_limit", product_id="id-1", http_status=429)
    assert _resolve_no_result_reason(result) == "http_429"


def test_should_not_retry_lock_skipped() -> None:
    """lock_skipped não deve acionar retry temporário — tem seu próprio mecanismo."""
    result = ScrapeResult(status="no_result", error_code="lock_skipped", product_id="id-1", http_status=200)
    assert _should_schedule_temporary_retry(result, "lock_skipped") is False


def test_should_not_retry_paused_competitor() -> None:
    """Concorrente pausado não deve acionar retry temporário."""
    result = ScrapeResult(status="no_result", error_code="paused", product_id="id-1", http_status=200)
    assert _should_schedule_temporary_retry(result, "paused") is False


def test_should_retry_rate_limit_failure() -> None:
    """Falha de rate limit deve agendar retry temporário."""
    result = ScrapeResult(status="error", error_code="rate_limit", product_id="id-1", http_status=429)
    assert _should_schedule_temporary_retry(result, "rate_limit") is True


def test_scraper_client_error_preserves_error_code() -> None:
    """ScraperClientError deve carregar o error_code estruturado para distinção pelo caller."""
    from shared.clients.scraper.scraper_client import ScraperClientError

    exc = ScraperClientError("no_result do scraper", status_code=422, error_code="no_result")
    assert exc.error_code == "no_result"
    assert exc.status_code == 422


def test_competitor_scrape_returns_error_for_422_no_result() -> None:
    """scrape_competitor_product retorna ScrapeResult(status='error') quando scraper retorna 422/no_result."""
    from types import SimpleNamespace
    from unittest.mock import patch
    from uuid import uuid4

    from shared.schemas.shared_schemas_products import CompetitorProductCreateScraping

    from market_alert.collectors.services.services_scraper_competitor import scrape_competitor_product

    monitored_id = uuid4()
    competitor_url = "https://competitor.com/produto/1"

    payload = CompetitorProductCreateScraping(
        monitored_product_id=monitored_id,
        product_url=competitor_url,
    )

    fake_fetch_result = SimpleNamespace(
        status_code=422,
        payload=None,
        headers={},
        error_code="no_result",
    )

    fake_db = Mock()

    with (
        patch(
            "market_alert.collectors.services.services_scraper_competitor.get_competitor_by_monitored_and_url",
            return_value=None,
        ),
        patch(
            "market_alert.collectors.services.services_scraper_competitor.execute_scraper_fetch",
            return_value=fake_fetch_result,
        ),
    ):
        result = scrape_competitor_product(
            db=fake_db,
            user_id=uuid4(),
            url=competitor_url,
            payload=payload,
        )

    assert result.status == "error"
    assert result.error_code == "no_result"
    assert result.http_status == 422
