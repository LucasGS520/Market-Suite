"""Testes unitarios do contrato backend->frontend de produtos monitorados."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from market_alert.enums.enums_products import MonitoredStatus
from market_alert.products.services.services_products import build_monitored_response


pytestmark = pytest.mark.unit


def _utc_datetime(hour: int) -> datetime:
    return datetime(2026, 4, 14, hour, 0, 0, tzinfo=timezone.utc)


def _json_utc(hour: int) -> str:
    return _utc_datetime(hour).isoformat().replace("+00:00", "Z")


def _make_monitored(**overrides: object) -> SimpleNamespace:
    base = {
        "id": uuid4(),
        "user_id": uuid4(),
        "display_name": "Monitorado contrato",
        "product_url": "https://store.example.com/products/contrato",
        "current_price": Decimal("199.90"),
        "currency": "BRL",
        "availability": True,
        "last_status": "collected",
        "status": MonitoredStatus.active,
        "thumbnail": "https://cdn.example.com/images/monitorado.png",
        "created_at": _utc_datetime(8),
        "last_checked": _utc_datetime(9),
        "last_scraped_at": _utc_datetime(9),
        "group_collected_at": _utc_datetime(9),
        "collected_at": _utc_datetime(9),
        "last_price_change_at": _utc_datetime(9),
        "stability_score": 2,
        "next_check_at": _utc_datetime(10),
        "is_featured": False,
        "paused": False,
        "paused_at": None,
        "last_collection_reason": None,
        "collection_outcome": None,
        "collection_error_class": None,
        "collection_retryable": None,
        "collection_next_retry_at": None,
        "collection_source_integrity": None,
        "collection_status_updated_at": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_monitored_response_exposes_semantic_collection_contract() -> None:
    retry_at = _utc_datetime(11)
    monitored = _make_monitored(
        current_price=None,
        last_status="error",
        last_scraped_at=None,
        group_collected_at=None,
        collected_at=None,
        collection_outcome="error",
        last_collection_reason="http_429",
        collection_error_class="transient",
        collection_retryable=True,
        collection_next_retry_at=retry_at,
        collection_source_integrity=False,
        collection_status_updated_at=_utc_datetime(10),
    )

    response = build_monitored_response(monitored, allow_missing_price=True)
    payload = response.model_dump(mode="json")

    assert response.display_status_priority == "collection_status"
    assert payload["collection_status"] == {
        "collection_outcome": "error",
        "collection_reason": "http_429",
        "collection_error_class": "transient",
        "collection_retryable": True,
        "collection_next_retry_at": _json_utc(11),
        "collection_source_integrity": False,
        "collection_updated_at": _json_utc(10),
        "collection_user_message_key": "retry_scheduled",
    }


def test_build_monitored_response_keeps_collection_status_null_before_first_attempt() -> None:
    monitored = _make_monitored(
        current_price=None,
        status=MonitoredStatus.pending,
        last_status="pending",
        last_scraped_at=None,
        group_collected_at=None,
        collected_at=None,
        last_checked=None,
    )

    response = build_monitored_response(monitored, allow_missing_price=True)
    payload = response.model_dump(mode="json")

    assert response.display_status == "collecting"
    assert response.display_status_priority is None
    assert payload["collection_status"] is None
