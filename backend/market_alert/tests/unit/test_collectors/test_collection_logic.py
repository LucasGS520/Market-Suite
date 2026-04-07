""" Testes unitarios para fluxo auxiliar de coleta compartilhada. """

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shared.schemas import ParserResponse

from market_alert.collectors.services import scraper_common


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
