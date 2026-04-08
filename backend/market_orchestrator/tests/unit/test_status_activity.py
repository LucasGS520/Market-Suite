from __future__ import annotations

from datetime import datetime, timezone

import pytest

import market_orchestrator.activities.status_activity as status_activity
import shared.infra.db.database as database_module
import shared.utils.redis_client as redis_client_module


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_query_collection_status_returns_completed_when_monitored_not_found(
    orchestrator_ids,
    session_local_factory,
    monkeypatch,
) -> None:
    session, session_local = session_local_factory(row=None)
    monkeypatch.setattr(database_module, "SessionLocal", session_local)

    result = await status_activity.query_collection_status(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result.completed is True
    assert result.last_error == "monitored_not_found"
    assert session.closed is True


@pytest.mark.asyncio
async def test_query_collection_status_returns_incomplete_when_last_scraped_is_missing(
    orchestrator_ids,
    row_factory,
    session_local_factory,
    monkeypatch,
) -> None:
    row = row_factory(last_scraped_at=None)
    session, session_local = session_local_factory(row=row)
    monkeypatch.setattr(database_module, "SessionLocal", session_local)

    result = await status_activity.query_collection_status(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result.completed is False
    assert result.last_error is None


@pytest.mark.asyncio
async def test_query_collection_status_accepts_completion_when_redis_is_unavailable(
    orchestrator_ids,
    row_factory,
    session_local_factory,
    monkeypatch,
) -> None:
    row = row_factory(last_scraped_at=datetime(2026, 4, 8, 12, 5, tzinfo=timezone.utc))
    session, session_local = session_local_factory(row=row)
    monkeypatch.setattr(database_module, "SessionLocal", session_local)
    monkeypatch.setattr(status_activity, "_read_dispatch_timestamp", lambda *args: None)

    result = await status_activity.query_collection_status(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result.completed is True
    assert result.last_error is None


@pytest.mark.asyncio
async def test_query_collection_status_accepts_completion_when_dispatch_timestamp_expired(
    orchestrator_ids,
    row_factory,
    session_local_factory,
    monkeypatch,
) -> None:
    row = row_factory(last_scraped_at=datetime(2026, 4, 8, 12, 5, tzinfo=timezone.utc))
    session, session_local = session_local_factory(row=row)
    monkeypatch.setattr(database_module, "SessionLocal", session_local)

    class _RedisExpired:
        def get(self, key):
            return None

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisExpired())

    result = await status_activity.query_collection_status(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result.completed is True
    assert result.last_error is None


@pytest.mark.asyncio
async def test_query_collection_status_compares_last_scraped_against_dispatch_timestamp(
    orchestrator_ids,
    row_factory,
    session_local_factory,
    monkeypatch,
) -> None:
    dispatch_ts = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    row = row_factory(last_scraped_at=datetime(2026, 4, 8, 12, 3, tzinfo=timezone.utc))
    session, session_local = session_local_factory(row=row)
    monkeypatch.setattr(database_module, "SessionLocal", session_local)
    monkeypatch.setattr(
        status_activity,
        "_read_dispatch_timestamp",
        lambda *args: dispatch_ts,
    )

    result = await status_activity.query_collection_status(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result.completed is True
    assert result.last_error is None


@pytest.mark.asyncio
async def test_query_collection_status_handles_database_failure(
    orchestrator_ids,
    session_local_factory,
    monkeypatch,
) -> None:
    session, session_local = session_local_factory(error=RuntimeError("db down"))
    monkeypatch.setattr(database_module, "SessionLocal", session_local)

    result = await status_activity.query_collection_status(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result.completed is False
    assert result.last_error == "db down"
    assert session.closed is True


def test_read_dispatch_timestamp_returns_none_when_redis_is_missing(
    orchestrator_ids,
    monkeypatch,
) -> None:
    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: None)

    result = status_activity._read_dispatch_timestamp(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result is None


def test_read_dispatch_timestamp_parses_iso_value_from_redis(
    orchestrator_ids,
    monkeypatch,
) -> None:
    expected = "2026-04-08T12:00:00+00:00"

    class _RedisStub:
        def get(self, key):
            return expected.encode()

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisStub())

    result = status_activity._read_dispatch_timestamp(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result == datetime.fromisoformat(expected)
