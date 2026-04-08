from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

import market_orchestrator.activities.snapshot_activity as snapshot_activity
import shared.utils.redis_client as redis_client_module
from market_orchestrator.enums.enums_workflow import WorkflowState
from market_orchestrator.schemas.schemas_snapshot import WorkflowSnapshot


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_persist_workflow_snapshot_writes_serialized_state_to_redis(
    monkeypatch,
) -> None:
    calls: list[dict] = []

    class _RedisStub:
        def setex(self, key, ttl, value):
            calls.append({"key": key, "ttl": ttl, "value": value})

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisStub())
    snapshot = WorkflowSnapshot(
        state=WorkflowState.WaitingTimer,
        next_run_at=datetime(2026, 4, 8, 12, 5, tzinfo=timezone.utc),
        last_run_at=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
        last_error="temporary-error",
        attempt_count=2,
        monitored_id="monitored-1",
    )

    await snapshot_activity.persist_workflow_snapshot(snapshot)

    assert calls == [
        {
            "key": snapshot_activity.settings.SNAPSHOT_KEY_TEMPLATE.format(
                monitored_id="monitored-1"
            ),
            "ttl": timedelta(seconds=snapshot_activity.settings.SNAPSHOT_TTL_SECONDS),
            "value": json.dumps(
                {
                    "state": "WaitingTimer",
                    "next_run_at": "2026-04-08T12:05:00+00:00",
                    "last_run_at": "2026-04-08T12:00:00+00:00",
                    "last_error": "temporary-error",
                    "attempt_count": 2,
                }
            ),
        }
    ]


@pytest.mark.asyncio
async def test_persist_workflow_snapshot_returns_when_redis_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: None)

    await snapshot_activity.persist_workflow_snapshot(
        WorkflowSnapshot(monitored_id="monitored-1")
    )


@pytest.mark.asyncio
async def test_cleanup_workflow_state_deletes_snapshot_key_when_redis_is_available(
    monkeypatch,
) -> None:
    deleted: list[str] = []

    class _RedisStub:
        def delete(self, key):
            deleted.append(key)

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisStub())

    await snapshot_activity.cleanup_workflow_state("monitored-1")

    assert deleted == [
        snapshot_activity.settings.SNAPSHOT_KEY_TEMPLATE.format(
            monitored_id="monitored-1"
        )
    ]


@pytest.mark.asyncio
async def test_cleanup_workflow_state_is_idempotent_when_redis_delete_returns_zero(
    monkeypatch,
) -> None:
    deleted: list[str] = []

    class _RedisStub:
        def delete(self, key):
            deleted.append(key)
            return 0

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisStub())

    await snapshot_activity.cleanup_workflow_state("monitored-1")

    assert len(deleted) == 1


@pytest.mark.asyncio
async def test_cleanup_workflow_state_returns_when_redis_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: None)

    await snapshot_activity.cleanup_workflow_state("monitored-1")
