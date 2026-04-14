from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

import market_orchestrator.worker as worker_module


pytestmark = pytest.mark.integration


def test_validate_infra_retries_until_database_and_redis_are_available(monkeypatch) -> None:
    sleep_calls: list[int] = []
    db_attempts = {"count": 0}
    redis_attempts = {"count": 0}

    class _ConnectionContext:
        def __enter__(self):
            db_attempts["count"] += 1
            if db_attempts["count"] < 3:
                raise SQLAlchemyError("db unavailable")
            return SimpleNamespace(execute=lambda statement: None)

        def __exit__(self, exc_type, exc, tb):
            return False

    class _EngineStub:
        def connect(self):
            return _ConnectionContext()

    class _RedisClientStub:
        def ping(self):
            redis_attempts["count"] += 1
            if redis_attempts["count"] < 2:
                raise RuntimeError("redis unavailable")

    monkeypatch.setattr("shared.infra.db.database.engine", _EngineStub())
    monkeypatch.setattr(
        "shared.utils.redis_client.get_redis_operational",
        lambda: _RedisClientStub(),
    )
    monkeypatch.setattr(worker_module.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    worker_module._validate_infra()

    assert db_attempts["count"] == 3
    assert redis_attempts["count"] == 2
    assert sleep_calls == [1, 2, 1]


def test_validate_infra_aborts_when_redis_never_recovers(monkeypatch) -> None:
    sleep_calls: list[int] = []

    class _ConnectionContext:
        def __enter__(self):
            return SimpleNamespace(execute=lambda statement: None)

        def __exit__(self, exc_type, exc, tb):
            return False

    class _EngineStub:
        def connect(self):
            return _ConnectionContext()

    class _RedisClientStub:
        def ping(self):
            raise RuntimeError("redis unavailable")

    monkeypatch.setattr("shared.infra.db.database.engine", _EngineStub())
    monkeypatch.setattr(
        "shared.utils.redis_client.get_redis_operational",
        lambda: _RedisClientStub(),
    )
    monkeypatch.setattr(worker_module.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    with pytest.raises(SystemExit, match="1"):
        worker_module._validate_infra()

    assert sleep_calls == [1, 2, 4]


@pytest.mark.asyncio
async def test_start_temporal_worker_registers_workflow_and_all_activities(
    worker_test_config,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class _WorkerStub:
        def __init__(
            self,
            client,
            *,
            task_queue,
            workflows,
            activities,
            workflow_runner,
        ) -> None:
            captured["client"] = client
            captured["task_queue"] = task_queue
            captured["workflows"] = workflows
            captured["activities"] = activities
            captured["workflow_runner"] = workflow_runner

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _LoopStub:
        def add_signal_handler(self, sig, callback):
            callback()

    fake_client = object()
    connect_mock = AsyncMock(return_value=fake_client)

    monkeypatch.setattr(worker_module, "settings", worker_test_config)
    monkeypatch.setattr(worker_module.Client, "connect", connect_mock)
    monkeypatch.setattr(worker_module, "Worker", _WorkerStub)
    monkeypatch.setattr(worker_module.asyncio, "get_running_loop", lambda: _LoopStub())

    await worker_module.start_temporal_worker()

    assert captured["client"] is fake_client
    assert captured["task_queue"] == worker_test_config.TEMPORAL_TASK_QUEUE
    assert captured["workflows"] == [worker_module.MonitoredProductWorkflow]
    assert [activity.__name__ for activity in captured["activities"]] == [
        "dispatch_collection",
        "query_collection_status",
        "persist_workflow_snapshot",
        "cleanup_workflow_state",
        "fetch_monitored_policy",
    ]
    connect_mock.assert_awaited_once_with(
        worker_test_config.temporal_target,
        namespace=worker_test_config.TEMPORAL_NAMESPACE,
    )


def test_run_worker_validates_infra_before_running_event_loop(monkeypatch) -> None:
    call_order: list[str] = []

    monkeypatch.setattr(
        worker_module,
        "_validate_infra",
        lambda: call_order.append("validate"),
    )

    def fake_asyncio_run(coro):
        call_order.append("run")
        coro.close()

    monkeypatch.setattr(worker_module.asyncio, "run", fake_asyncio_run)

    worker_module.run_worker()

    assert call_order == ["validate", "run"]
