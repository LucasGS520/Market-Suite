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


# ---------------------------------------------------------------------------
# _read_collection_result
# ---------------------------------------------------------------------------

def test_read_collection_result_returns_none_when_redis_unavailable(
    orchestrator_ids,
    monkeypatch,
) -> None:
    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: None)

    result = status_activity._read_collection_result(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result is None


def test_read_collection_result_returns_dict_when_key_present(
    orchestrator_ids,
    monkeypatch,
) -> None:
    import json

    stored = {"outcome": "success", "reason": ""}
    raw = json.dumps(stored).encode()

    class _RedisStub:
        def get(self, key):
            return raw

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisStub())

    result = status_activity._read_collection_result(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result == stored


def test_read_collection_result_returns_none_when_key_absent(
    orchestrator_ids,
    monkeypatch,
) -> None:
    class _RedisStub:
        def get(self, key):
            return None

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisStub())

    result = status_activity._read_collection_result(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result is None


def test_read_collection_result_returns_none_on_exception(
    orchestrator_ids,
    monkeypatch,
) -> None:
    class _BrokenRedis:
        def get(self, key):
            raise RuntimeError("redis down")

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _BrokenRedis())

    result = status_activity._read_collection_result(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result is None


# ---------------------------------------------------------------------------
# query_collection_status — result key fast path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_collection_status_result_key_success_outcome_returns_completed(
    orchestrator_ids,
    monkeypatch,
) -> None:
    import json

    raw = json.dumps({"outcome": "success", "reason": ""}).encode()

    class _RedisStub:
        def get(self, key):
            return raw

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisStub())

    result = await status_activity.query_collection_status(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result.completed is True
    assert result.last_error is None


@pytest.mark.asyncio
async def test_query_collection_status_result_key_not_modified_returns_completed(
    orchestrator_ids,
    monkeypatch,
) -> None:
    import json

    raw = json.dumps({"outcome": "not_modified", "reason": ""}).encode()

    class _RedisStub:
        def get(self, key):
            return raw

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisStub())

    result = await status_activity.query_collection_status(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result.completed is True
    assert result.last_error is None


@pytest.mark.asyncio
async def test_query_collection_status_result_key_lock_skipped_returns_completed_no_error(
    orchestrator_ids,
    monkeypatch,
) -> None:
    """lock_skipped é transitório — workflow deve retomar WaitingTimer, não Backoff."""
    import json

    raw = json.dumps({"outcome": "no_result", "reason": "lock_skipped"}).encode()

    class _RedisStub:
        def get(self, key):
            return raw

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisStub())

    result = await status_activity.query_collection_status(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result.completed is True
    assert result.last_error is None


@pytest.mark.asyncio
async def test_query_collection_status_result_key_unknown_reason_returns_last_error(
    orchestrator_ids,
    monkeypatch,
) -> None:
    """Reason desconhecido (ex: lock_exhausted removido do catálogo) não é neutro — vai para Backoff."""
    import json

    raw = json.dumps({"outcome": "no_result", "reason": "lock_exhausted"}).encode()

    class _RedisStub:
        def get(self, key):
            return raw

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisStub())

    result = await status_activity.query_collection_status(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result.completed is True
    assert result.last_error == "lock_exhausted"
    assert result.error_class == "transient"


@pytest.mark.asyncio
async def test_query_collection_status_result_key_structural_failure_returns_last_error(
    orchestrator_ids,
    monkeypatch,
) -> None:
    """Falha real de domínio (parser falhou) deve ir para Backoff via last_error."""
    import json

    raw = json.dumps({"outcome": "error", "reason": "parse_price_failed"}).encode()

    class _RedisStub:
        def get(self, key):
            return raw

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisStub())

    result = await status_activity.query_collection_status(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result.completed is True
    assert result.last_error == "parse_price_failed"
    assert result.error_class == "structural"


@pytest.mark.asyncio
async def test_query_collection_status_result_key_error_outcome_returns_last_error(
    orchestrator_ids,
    monkeypatch,
) -> None:
    """outcome=error com reason deve propagar reason como last_error."""
    import json

    raw = json.dumps({"outcome": "error", "reason": "scraper_client_error"}).encode()

    class _RedisStub:
        def get(self, key):
            return raw

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisStub())

    result = await status_activity.query_collection_status(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result.completed is True
    assert result.last_error == "scraper_client_error"
    assert result.error_class == "transient"


@pytest.mark.asyncio
async def test_query_collection_status_result_key_domain_empty_returns_error_class_and_observability_fields(
    orchestrator_ids,
    monkeypatch,
) -> None:
    import json

    raw = json.dumps({"outcome": "no_result", "reason": "parse_empty"}).encode()
    captured_logs: list[dict[str, object]] = []

    class _RedisStub:
        def get(self, key):
            return raw

    class _LoggerStub:
        def info(self, event, **kwargs):
            captured_logs.append({"event": event, **kwargs})

        def warning(self, event, **kwargs):
            captured_logs.append({"event": event, **kwargs})

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisStub())
    monkeypatch.setattr(status_activity, "logger", _LoggerStub())

    result = await status_activity.query_collection_status(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["correlation_id"],
    )

    assert result.completed is True
    assert result.last_error == "parse_empty"
    assert result.error_class == "domain_empty"
    assert captured_logs[-1]["semantic_category"] == "domain_empty"
    assert captured_logs[-1]["source_integrity"] is True


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
