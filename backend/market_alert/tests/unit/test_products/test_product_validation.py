""" Testes unitarios para regras puras do ciclo de vida de produtos. """

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from shared.scheduling import EVENT_AVAILABILITY_CHANGED, EVENT_PRICE_CHANGED, EVENT_STANDARD, STABILITY_UNSTABLE

from market_alert.enums.enums_products import MonitoredStatus
from market_alert.products.domain import product_lifecycle


pytestmark = pytest.mark.unit


def test_validate_status_transition_allows_pending_to_active() -> None:
    assert product_lifecycle.validate_status_transition(
        MonitoredStatus.pending,
        MonitoredStatus.active,
    ) is True


def test_validate_status_transition_rejects_active_to_pending() -> None:
    assert product_lifecycle.validate_status_transition(
        MonitoredStatus.active,
        MonitoredStatus.pending,
    ) is False


def test_resolve_scheduling_event_prioritizes_price_change() -> None:
    event = product_lifecycle.resolve_scheduling_event(
        price_changed=True,
        availability_changed=True,
    )

    assert event == EVENT_PRICE_CHANGED


def test_resolve_scheduling_event_falls_back_to_availability() -> None:
    event = product_lifecycle.resolve_scheduling_event(
        price_changed=False,
        availability_changed=True,
    )

    assert event == EVENT_AVAILABILITY_CHANGED


def test_resolve_scheduling_event_defaults_to_standard() -> None:
    event = product_lifecycle.resolve_scheduling_event(
        price_changed=False,
        availability_changed=False,
    )

    assert event == EVENT_STANDARD


def test_update_price_change_tracking_updates_group_and_stability() -> None:
    monitored = SimpleNamespace(
        id=uuid4(),
        group_collected_at=None,
        last_price_change_at=None,
        stability_score=99,
    )
    collected_at = datetime(2026, 4, 7, 10, 0, 0)

    product_lifecycle.update_price_change_tracking(
        monitored,
        new_price=Decimal("150.00"),
        old_price=Decimal("120.00"),
        collected_at=collected_at,
    )

    assert monitored.group_collected_at.tzinfo is not None
    assert monitored.last_price_change_at == monitored.group_collected_at
    assert monitored.stability_score == STABILITY_UNSTABLE


def test_update_competitor_price_change_tracking_ignores_same_price() -> None:
    competitor = SimpleNamespace(
        id=uuid4(),
        monitored_product_id=uuid4(),
        last_price_change_at=None,
    )

    product_lifecycle.update_competitor_price_change_tracking(
        competitor,
        new_price=Decimal("90.00"),
        old_price=Decimal("90.00"),
        collected_at=datetime(2026, 4, 7, 10, 0, 0),
    )

    assert competitor.last_price_change_at is None
