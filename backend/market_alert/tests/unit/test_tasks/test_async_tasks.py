from __future__ import annotations

from contextlib import contextmanager
import json
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import market_alert.collectors.tasks.collector_product_task as collector_task_module
import market_alert.comparisons.tasks.compare_prices_task as compare_task_module
import market_alert.infrastructure.celery.domain_task_enqueuer as enqueuer_module
import market_alert.infrastructure.celery.dlq_base_task as dlq_base_task_module
import market_alert.notifications.tasks.notifications_enqueue_task as enqueue_task_module
import market_alert.notifications.tasks.send_notification_task as send_task_module
import shared.utils.redis_client as redis_client_module


pytestmark = pytest.mark.unit


class _SessionStub:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@contextmanager
def _task_request(task, **kwargs):
    task.push_request(**kwargs)
    try:
        yield
    finally:
        task.pop_request()


def _valid_collection_payload(**overrides: str) -> dict[str, str]:
    payload = {
        "version": 1,
        "kind": "monitored",
        "monitored_id": str(uuid4()),
        "url": "https://store.example.com/products/task-monitored",
        "trace_id": str(uuid4()),
        "user_id": str(uuid4()),
        "name": "Produto monitorado",
    }
    payload.update(overrides)
    return payload


def test_domain_task_enqueuer_enqueue_comparison_routes_queue_and_trace_headers(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        enqueuer_module.celery_app,
        "send_task",
        lambda task_name, **kwargs: calls.append({"task_name": task_name, **kwargs}),
    )

    monitored_id = uuid4()

    enqueuer_module.DomainTaskEnqueuer().enqueue_comparison(
        monitored_id,
        reason="material_change",
        trace_id="trace-compare",
    )

    assert calls == [
        {
            "task_name": "market_alert.comparisons.tasks.compare_prices_task.compare_prices_task",
            "args": [str(monitored_id)],
            "kwargs": {"trace_id": "trace-compare"},
            "headers": {"trace_id": "trace-compare"},
            "queue": "compare",
        }
    ]


def test_domain_task_enqueuer_enqueue_notification_omits_trace_headers_when_absent(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        enqueuer_module.celery_app,
        "send_task",
        lambda task_name, **kwargs: calls.append({"task_name": task_name, **kwargs}),
    )

    notification_id = uuid4()

    enqueuer_module.DomainTaskEnqueuer().enqueue_notification(notification_id)

    assert calls == [
        {
            "task_name": "market_alert.notifications.tasks.send_notification_task.send_notification_task",
            "args": [str(notification_id)],
            "kwargs": {"trace_id": None},
            "headers": {},
            "queue": "notifications",
        }
    ]


def test_collect_product_task_returns_error_for_invalid_payload(monkeypatch) -> None:
    with _task_request(
        collector_task_module.collect_product_task,
        id="collect-task-1",
        retries=0,
        delivery_info={"routing_key": "scraping"},
    ):
        result = collector_task_module.collect_product_task.run({"kind": "monitored"})

    assert result == {
        "outcome": "error",
        "status": "error",
        "reason": "invalid_payload",
        "next_retry_at": None,
        "product_id": None,
    }


def test_collect_product_task_schedules_retry_for_lock_skipped(monkeypatch) -> None:
    payload = _valid_collection_payload()
    retry_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        collector_task_module.collect_product_task,
        "retry",
        lambda **kwargs: retry_calls.append(kwargs),
        raising=False,
    )
    monkeypatch.setattr(collector_task_module, "SessionLocal", lambda: _SessionStub())
    monkeypatch.setattr(
        collector_task_module,
        "collect_product",
        lambda *args, **kwargs: ("no_result", SimpleNamespace(error_code="lock_skipped"), None),
    )
    monkeypatch.setattr(
        collector_task_module.RetryPolicy,
        "compute_lock_retry_delay",
        lambda attempt: 7.5,
    )
    monkeypatch.setattr(collector_task_module, "_should_block_invalid_url", lambda result: False)
    monkeypatch.setattr(
        collector_task_module,
        "_should_schedule_temporary_retry",
        lambda result, reason: False,
    )

    with _task_request(
        collector_task_module.collect_product_task,
        id="collect-task-2",
        retries=1,
        delivery_info={"routing_key": "scraping"},
    ):
        result = collector_task_module.collect_product_task.run(payload=payload)

    assert retry_calls == [
        {
            "countdown": 7.5,
            "max_retries": collector_task_module.LOCK_RETRY_MAX_RETRIES,
            "throw": False,
        }
    ]
    assert result["outcome"] == "no_result"
    assert result["product_id"] == payload["monitored_id"]


def test_collect_product_task_writes_contract_result_to_redis_for_status_activity(monkeypatch) -> None:
    payload = _valid_collection_payload(correlation_id=str(uuid4()))
    redis_calls: list[dict[str, object]] = []

    class _RedisStub:
        def setex(self, key, ttl, value):
            redis_calls.append({"key": key, "ttl": ttl, "value": value})

    monkeypatch.setattr(collector_task_module, "SessionLocal", lambda: _SessionStub())
    monkeypatch.setattr(
        collector_task_module,
        "collect_product",
        lambda *args, **kwargs: ("error", SimpleNamespace(error_code="anti_bot_page"), "challenge_detected"),
    )
    monkeypatch.setattr(collector_task_module, "_should_block_invalid_url", lambda result: False)
    monkeypatch.setattr(
        collector_task_module,
        "_should_schedule_temporary_retry",
        lambda result, reason: False,
    )
    monkeypatch.setattr(redis_client_module, "get_redis_operational", lambda: _RedisStub())

    with _task_request(
        collector_task_module.collect_product_task,
        id="collect-task-redis",
        retries=0,
        delivery_info={"routing_key": "scraping"},
    ):
        result = collector_task_module.collect_product_task.run(payload=payload)

    assert result == {
        "outcome": "error",
        "status": "error",
        "reason": "challenge_detected",
        "next_retry_at": None,
        "product_id": payload["monitored_id"],
    }
    assert redis_calls == [
        {
            "key": f"{collector_task_module._COLLECTION_RESULT_KEY_PREFIX}:{payload['monitored_id']}:{payload['correlation_id']}",
            "ttl": collector_task_module._COLLECTION_RESULT_TTL_SECONDS,
            "value": json.dumps(
                {
                    "outcome": "error",
                    "reason": "challenge_detected",
                    "error_class": "transient",
                    "source_integrity": False,
                    "next_retry_at": None,
                    "schema_version": 1,
                }
            ),
        }
    ]


def test_compare_prices_task_skips_notifications_when_flags_indicate_no_change(monkeypatch) -> None:
    monitored_id = uuid4()

    monkeypatch.setattr(compare_task_module, "SessionLocal", lambda: _SessionStub())
    monkeypatch.setattr(
        compare_task_module,
        "run_price_comparison",
        lambda db, monitored_uuid: {
            "summary": {"competitors_with_price_count": 2},
            "lowest_competitor": Decimal("189.90"),
            "highest_competitor": Decimal("205.00"),
        },
    )
    monkeypatch.setattr(
        compare_task_module,
        "evaluate_and_create_notifications",
        lambda *args, **kwargs: pytest.fail("notifications should be skipped"),
    )

    with _task_request(
        compare_task_module.compare_prices_task,
        id="compare-task-1",
        delivery_info={"routing_key": "compare"},
    ):
        result = compare_task_module.compare_prices_task.run(
            monitored_id=str(monitored_id),
            price_changed=False,
            availability_changed=False,
            trace_id="trace-compare-skip",
        )

    assert result is None


def test_compare_prices_task_evaluates_and_enqueues_notifications(monkeypatch) -> None:
    monitored_id = uuid4()
    user_id = uuid4()
    captured_snapshots: dict[str, object] = {}
    enqueued: list[dict[str, object]] = []

    monkeypatch.setattr(compare_task_module, "SessionLocal", lambda: _SessionStub())
    monkeypatch.setattr(
        compare_task_module,
        "run_price_comparison",
        lambda db, monitored_uuid: {
            "summary": {"competitors_with_price_count": 1},
            "lowest_competitor": Decimal("189.90"),
            "highest_competitor": Decimal("205.00"),
        },
    )
    monkeypatch.setattr(
        compare_task_module,
        "get_monitored_product_by_id",
        lambda db, monitored_uuid: SimpleNamespace(id=monitored_uuid, user_id=user_id, availability=True),
    )
    monkeypatch.setattr(
        compare_task_module,
        "get_user_by_id",
        lambda db, owner_id: SimpleNamespace(id=owner_id),
    )
    monkeypatch.setattr(
        compare_task_module,
        "fetch_recent_prices",
        lambda db, monitored_uuid: (Decimal("100.00"), Decimal("125.00")),
    )

    def _evaluate(monitored, previous_snapshot, current_snapshot, **kwargs):
        captured_snapshots["previous"] = previous_snapshot
        captured_snapshots["current"] = current_snapshot
        captured_snapshots["trace_id"] = kwargs["trace_id"]
        return ["notif-1"]

    monkeypatch.setattr(compare_task_module, "evaluate_and_create_notifications", _evaluate)
    monkeypatch.setattr(
        compare_task_module,
        "enqueue_pending_notifications",
        lambda db, notification_ids, trace_id: enqueued.append(
            {"notification_ids": notification_ids, "trace_id": trace_id}
        ),
    )

    with _task_request(
        compare_task_module.compare_prices_task,
        id="compare-task-2",
        delivery_info={"routing_key": "compare"},
    ):
        compare_task_module.compare_prices_task.run(
            monitored_id=str(monitored_id),
            price_changed=True,
            availability_changed=None,
            trace_id="trace-compare-ok",
        )

    assert captured_snapshots["previous"]["price"] == Decimal("100.00")
    assert captured_snapshots["current"]["price"] == Decimal("125.00")
    assert captured_snapshots["current"]["price_delta_percent"] == 25.0
    assert enqueued == [
        {
            "notification_ids": ["notif-1"],
            "trace_id": "trace-compare-ok",
        }
    ]


def test_enqueue_notifications_task_delegates_with_session_and_trace(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(enqueue_task_module, "SessionLocal", lambda: _SessionStub())
    monkeypatch.setattr(
        enqueue_task_module,
        "enqueue_pending_notifications",
        lambda db, notification_ids, trace_id: calls.append(
            {
                "db": db,
                "notification_ids": notification_ids,
                "trace_id": trace_id,
            }
        ) or 2,
    )

    with _task_request(enqueue_task_module.enqueue_notifications_task, id="enqueue-task-1"):
        result = enqueue_task_module.enqueue_notifications_task.run(["1", "2"])

    assert result == 2
    assert calls[0]["notification_ids"] == ["1", "2"]
    assert calls[0]["trace_id"] == "enqueue-task-1"


def test_send_notification_task_uses_header_trace_id_fallback(monkeypatch) -> None:
    trace_ids: list[str] = []
    processed_ids: list[UUID] = []
    notification_id = uuid4()

    monkeypatch.setattr(send_task_module, "set_trace_id", lambda value: trace_ids.append(value))
    monkeypatch.setattr(send_task_module, "SessionLocal", lambda: _SessionStub())
    monkeypatch.setattr(
        send_task_module,
        "process_notification",
        lambda db, notification_id: processed_ids.append(notification_id) or False,
    )

    with _task_request(
        send_task_module.send_notification_task,
        id="send-task-1",
        headers={"trace_id": "trace-header-send"},
    ):
        send_task_module.send_notification_task.run(str(notification_id))

    assert trace_ids == ["trace-header-send"]
    assert processed_ids == [notification_id]


def test_send_notification_task_dlq_on_failure_uses_trace_header_fallback(monkeypatch) -> None:
    dlq_calls: list[dict[str, object]] = []

    monkeypatch.setattr(send_task_module.send_notification_task, "max_retries", 3, raising=False)
    monkeypatch.setattr(dlq_base_task_module, "write_to_dlq", lambda **kwargs: dlq_calls.append(kwargs))

    exc = RuntimeError("boom")
    with _task_request(
        send_task_module.send_notification_task,
        retries=2,
        id="send-task-2",
        headers={"trace_id": "trace-header-dlq"},
        delivery_info={"routing_key": "notifications"},
    ):
        send_task_module.send_notification_task.on_failure(
            exc,
            task_id="celery-task-id",
            args=("notification-id",),
            kwargs={},
            einfo=None,
        )

    assert len(dlq_calls) == 1
    assert dlq_calls[0]["task_id"] == "celery-task-id"
    assert dlq_calls[0]["task_name"] == send_task_module.send_notification_task.name
    assert dlq_calls[0]["queue"] == "notifications"
    assert dlq_calls[0]["exception"] is exc
    assert dlq_calls[0]["trace_id"] == "trace-header-dlq"
    assert dlq_calls[0]["retry_count"] == 2
    assert dlq_calls[0]["max_retries"] == 3
