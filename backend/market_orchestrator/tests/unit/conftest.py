from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from shared.schemas.shared_schemas_orchestrator import CollectionPolicy

from market_orchestrator.workflow import MonitoredProductWorkflow


@pytest.fixture
def workflow_now() -> datetime:
    return datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def workflow_policy() -> CollectionPolicy:
    return CollectionPolicy(
        interval_seconds=60,
        backoff_max_attempts=3,
        backoff_base_seconds=5,
        stability_score=0,
        scheduling_reason="test-default",
    )


@pytest.fixture
def workflow_instance(workflow_policy) -> MonitoredProductWorkflow:
    instance = MonitoredProductWorkflow()
    instance._monitored_id = "monitored-1"
    instance._user_id = "user-1"
    instance._policy = workflow_policy
    return instance


@pytest.fixture
def orchestrator_ids() -> dict[str, str]:
    return {
        "monitored_id": str(uuid4()),
        "user_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "trace_id": str(uuid4()),
    }


@pytest.fixture
def row_factory():
    def _build(**kwargs):
        return SimpleNamespace(**kwargs)

    return _build


@pytest.fixture
def session_local_factory():
    def _build(*, row=None, error: Exception | None = None):
        session = SimpleNamespace(closed=False, executed=[])

        def execute(statement, params):
            session.executed.append({"statement": statement, "params": params})
            if error is not None:
                raise error
            return SimpleNamespace(fetchone=lambda: row)

        def close():
            session.closed = True

        session.execute = execute
        session.close = close
        return session, (lambda: session)

    return _build
