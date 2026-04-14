from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import market_orchestrator.activities.policy_activity as policy_activity
import shared.infra.db.database as database_module


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_fetch_monitored_policy_returns_computed_schedule_for_existing_product(
    orchestrator_ids,
    row_factory,
    session_local_factory,
    monkeypatch,
) -> None:
    row = row_factory(
        status="active",
        last_price_change_at=None,
        last_scraped_at=datetime(2026, 4, 8, 11, 55, tzinfo=timezone.utc),
        group_collected_at=None,
        created_at=datetime(2026, 4, 8, 11, 0, tzinfo=timezone.utc),
        next_check_at=datetime(2026, 4, 8, 12, 30, tzinfo=timezone.utc),
        stability_score=4,
        paused=True,
    )
    session, session_local = session_local_factory(row=row)
    monkeypatch.setattr(database_module, "SessionLocal", session_local)
    monkeypatch.setattr(
        policy_activity,
        "calculate_schedule",
        lambda ctx, event_type: SimpleNamespace(
            interval_seconds=180,
            next_check_at=datetime(2026, 4, 8, 12, 3, tzinfo=timezone.utc),
            stability_score=7,
            reason="scheduled-window",
        ),
    )

    result = await policy_activity.fetch_monitored_policy(orchestrator_ids["monitored_id"])

    assert result.interval_seconds == 180
    assert result.next_check_at == "2026-04-08T12:03:00+00:00"
    assert result.paused is True
    assert result.stability_score == 7
    assert result.scheduling_reason == "scheduled-window"
    assert session.closed is True


@pytest.mark.asyncio
async def test_fetch_monitored_policy_returns_product_not_found_fallback(
    orchestrator_ids,
    session_local_factory,
    monkeypatch,
) -> None:
    session, session_local = session_local_factory(row=None)
    monkeypatch.setattr(database_module, "SessionLocal", session_local)

    result = await policy_activity.fetch_monitored_policy(orchestrator_ids["monitored_id"])

    assert result.interval_seconds == 3600
    assert result.paused is False
    assert result.scheduling_reason == "product_not_found_fallback"


@pytest.mark.asyncio
async def test_fetch_monitored_policy_returns_error_fallback_when_schedule_calculation_fails(
    orchestrator_ids,
    row_factory,
    session_local_factory,
    monkeypatch,
) -> None:
    row = row_factory(
        status="active",
        last_price_change_at=None,
        last_scraped_at=None,
        group_collected_at=None,
        created_at=datetime(2026, 4, 8, 11, 0, tzinfo=timezone.utc),
        next_check_at=None,
        stability_score=0,
        paused=False,
    )
    session, session_local = session_local_factory(row=row)
    monkeypatch.setattr(database_module, "SessionLocal", session_local)

    def raise_schedule_error(ctx, event_type):
        raise RuntimeError("schedule broke")

    monkeypatch.setattr(policy_activity, "calculate_schedule", raise_schedule_error)

    result = await policy_activity.fetch_monitored_policy(orchestrator_ids["monitored_id"])

    assert result == policy_activity._FALLBACK_OUTPUT
    assert session.closed is True
