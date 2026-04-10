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


pytestmark = pytest.mark.unit


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


def test_resolve_no_result_reason_no_result_falls_to_validation() -> None:
    """Scraper retornando no_result (sem dados extraídos) mantém razão 'validation'."""
    result = ScrapeResult(status="no_result", error_code="no_result", product_id="id-1", http_status=422)
    assert _resolve_no_result_reason(result) == "validation"


def test_resolve_no_result_reason_rate_limit() -> None:
    """Rate limit é identificado explicitamente como 'rate_limit'."""
    result = ScrapeResult(status="no_result", error_code="rate_limit", product_id="id-1", http_status=429)
    assert _resolve_no_result_reason(result) == "rate_limit"


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
