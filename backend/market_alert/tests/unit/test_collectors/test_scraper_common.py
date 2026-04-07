""" Testes unitarios para sanitizacao e validacao em scraper_common. """

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from shared.clients.scraper.scraper_client import ScraperClientError
from shared.schemas import ParserResponse

from market_alert.collectors.services import scraper_common


pytestmark = pytest.mark.unit


def test_resolve_conditional_headers_normalizes_naive_datetime() -> None:
    entity = SimpleNamespace(
        etag="etag-1",
        last_modified=datetime(2026, 4, 7, 10, 0, 0),
    )

    etag, last_modified = scraper_common.resolve_conditional_headers(entity)

    assert etag == "etag-1"
    assert last_modified.tzinfo == timezone.utc


def test_compute_force_refresh_respects_ttl_threshold() -> None:
    should_refresh = scraper_common.compute_force_refresh(
        datetime(2026, 4, 7, 9, 0, 0, tzinfo=timezone.utc),
        now=datetime(2026, 4, 7, 10, 1, 0, tzinfo=timezone.utc),
        ttl_seconds=3600,
    )

    assert should_refresh is True


def test_ensure_price_returns_decimal_for_valid_payload() -> None:
    payload = ParserResponse(name="Produto", current_price=Decimal("10.50"))

    assert scraper_common.ensure_price(payload, "https://example.com") == Decimal("10.50")


def test_ensure_price_rejects_missing_value() -> None:
    payload = ParserResponse(name="Produto", current_price=None)

    with pytest.raises(ScraperClientError, match="sem pre"):
        scraper_common.ensure_price(payload, "https://example.com")


def test_ensure_name_sanitizes_text() -> None:
    payload = ParserResponse(name="  Nome do Produto  ", current_price=Decimal("10.50"))

    assert scraper_common.ensure_name(payload, "https://example.com") == "Nome do Produto"


def test_normalize_currency_code_returns_uppercase_alnum() -> None:
    assert scraper_common.normalize_currency_code(" br-l ") == "BRL"


def test_to_float_returns_none_for_invalid_value() -> None:
    assert scraper_common.to_float("invalid") is None
