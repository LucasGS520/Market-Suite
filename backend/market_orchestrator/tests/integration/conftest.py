from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from temporalio.testing import WorkflowEnvironment

from shared.schemas.shared_schemas_orchestrator import CollectionPolicy, WorkflowInput


@pytest.fixture
def integration_ids() -> dict[str, str]:
    return {
        "monitored_id": str(uuid4()),
        "user_id": str(uuid4()),
    }


@pytest.fixture
def integration_policy() -> CollectionPolicy:
    return CollectionPolicy(
        interval_seconds=1,
        backoff_max_attempts=3,
        backoff_base_seconds=1,
        stability_score=0,
        scheduling_reason="integration-default",
    )


@pytest.fixture
def workflow_input(integration_ids, integration_policy) -> WorkflowInput:
    return WorkflowInput(
        monitored_id=integration_ids["monitored_id"],
        user_id=integration_ids["user_id"],
        policy=integration_policy,
    )


@pytest.fixture
def integration_now() -> datetime:
    return datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def worker_test_config() -> SimpleNamespace:
    return SimpleNamespace(
        temporal_target="test-server:7233",
        TEMPORAL_NAMESPACE="default",
        TEMPORAL_TASK_QUEUE="market-orchestrator-integration",
    )


@pytest.fixture
def mark_high_cost_integration() -> pytest.MarkDecorator:
    return pytest.mark.integration_high_cost


@pytest_asyncio.fixture
async def temporal_test_environment():
    env = await WorkflowEnvironment.start_time_skipping()
    try:
        yield env
    finally:
        await env.shutdown()


@pytest.fixture
def wait_until():
    async def _wait_until(predicate, *, timeout: float = 5.0, interval: float = 0.01):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if predicate():
                return
            await asyncio.sleep(interval)
        raise AssertionError("Condition was not satisfied before timeout")

    return _wait_until
