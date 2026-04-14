from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from temporalio.exceptions import ApplicationError

import market_orchestrator.activities.dispatch_activity as dispatch_activity
import shared.utils.redis_client as redis_client_module
from shared.schemas.shared_schemas_orchestrator import CollectionPayload


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_dispatch_collection_raises_when_monitored_url_is_missing(
    orchestrator_ids,
    monkeypatch,
) -> None:
    monkeypatch.setattr(dispatch_activity, "_fetch_monitored_url", lambda monitored_id: None)

    with pytest.raises(ApplicationError, match="não encontrado ou sem URL") as exc_info:
        await dispatch_activity.dispatch_collection(
            orchestrator_ids["monitored_id"],
            orchestrator_ids["user_id"],
            orchestrator_ids["correlation_id"],
            orchestrator_ids["trace_id"],
        )

    assert exc_info.value.non_retryable is True


@pytest.mark.asyncio
async def test_dispatch_collection_raises_for_invalid_payload(
    orchestrator_ids,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        dispatch_activity,
        "_fetch_monitored_url",
        lambda monitored_id: "https://example.com/product",
    )

    with pytest.raises(ApplicationError, match="Payload inválido") as exc_info:
        await dispatch_activity.dispatch_collection(
            "not-a-uuid",
            orchestrator_ids["user_id"],
            orchestrator_ids["correlation_id"],
            orchestrator_ids["trace_id"],
        )

    assert exc_info.value.non_retryable is True


@pytest.mark.asyncio
async def test_dispatch_collection_enqueues_payload_and_persists_dispatch_timestamp(
    orchestrator_ids,
    monkeypatch,
) -> None:
    sent_payloads: list[dict] = []
    redis_calls: list[dict] = []

    class _RedisStub:
        def setex(self, key, ttl, value):
            redis_calls.append({"key": key, "ttl": ttl, "value": value})

    monkeypatch.setattr(
        dispatch_activity,
        "_fetch_monitored_url",
        lambda monitored_id: "https://example.com/product",
    )
    monkeypatch.setattr(
        "shared.clients.celery.task_dispatcher.send_collection_task",
        lambda payload: sent_payloads.append(payload) or "task-1",
    )
    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisStub())
    monkeypatch.setattr(
        dispatch_activity,
        "datetime",
        SimpleNamespace(now=lambda tz=None: datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)),
    )

    result = await dispatch_activity.dispatch_collection(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["user_id"],
        orchestrator_ids["correlation_id"],
        orchestrator_ids["trace_id"],
        force_compare=True,
    )

    assert result.success is True
    assert len(sent_payloads) == 1
    payload = CollectionPayload.model_validate(sent_payloads[0])
    assert str(payload.monitored_id) == orchestrator_ids["monitored_id"]
    assert str(payload.user_id) == orchestrator_ids["user_id"]
    assert payload.trace_id == orchestrator_ids["trace_id"]
    assert payload.force_compare == "true"
    assert redis_calls == [
        {
            "key": (
                f"{dispatch_activity._DISPATCH_KEY_PREFIX}:"
                f"{orchestrator_ids['monitored_id']}:{orchestrator_ids['correlation_id']}"
            ),
            "ttl": dispatch_activity._DISPATCH_TTL_SECONDS,
            "value": "2026-04-08T12:00:00+00:00",
        }
    ]


@pytest.mark.asyncio
async def test_dispatch_collection_keeps_success_when_redis_store_fails(
    orchestrator_ids,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        dispatch_activity,
        "_fetch_monitored_url",
        lambda monitored_id: "https://example.com/product",
    )
    monkeypatch.setattr(
        "shared.clients.celery.task_dispatcher.send_collection_task",
        lambda payload: "task-1",
    )

    class _RedisBroken:
        def setex(self, key, ttl, value):
            raise RuntimeError("redis down")

    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisBroken())

    result = await dispatch_activity.dispatch_collection(
        orchestrator_ids["monitored_id"],
        orchestrator_ids["user_id"],
        orchestrator_ids["correlation_id"],
        orchestrator_ids["trace_id"],
    )

    assert result.success is True


def test_fetch_monitored_url_returns_normalized_url_when_available(
    orchestrator_ids,
    row_factory,
    session_local_factory,
    monkeypatch,
) -> None:
    row = row_factory(
        normalized_url="https://example.com/normalized",
        product_url="https://example.com/fallback",
    )
    session, session_local = session_local_factory(row=row)
    monkeypatch.setattr(dispatch_activity, "SessionLocal", session_local)

    result = dispatch_activity._fetch_monitored_url(orchestrator_ids["monitored_id"])

    assert result == "https://example.com/normalized"
    assert session.closed is True


def test_fetch_monitored_url_falls_back_to_product_url(
    orchestrator_ids,
    row_factory,
    session_local_factory,
    monkeypatch,
) -> None:
    row = row_factory(
        normalized_url=None,
        product_url="https://example.com/fallback",
    )
    session, session_local = session_local_factory(row=row)
    monkeypatch.setattr(dispatch_activity, "SessionLocal", session_local)

    result = dispatch_activity._fetch_monitored_url(orchestrator_ids["monitored_id"])

    assert result == "https://example.com/fallback"
    assert session.closed is True
