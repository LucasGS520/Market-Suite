from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from temporalio import activity
from temporalio.worker import Worker

from market_orchestrator.enums.enums_workflow import WorkflowState
from market_orchestrator.schemas.schemas_snapshot import WorkflowSnapshot
from market_orchestrator.workflow import MonitoredProductWorkflow
from shared.clients.temporal.orchestrator_client import TemporalOrchestrationClient
from shared.schemas.shared_schemas_orchestrator import (
    DispatchActivityOutput,
    PolicyActivityOutput,
    QueryStatusOutput,
    ResumeSignalPayload,
)


pytestmark = [pytest.mark.integration, pytest.mark.integration_high_cost]


def _snapshot_state_name(snapshot: WorkflowSnapshot) -> str | None:
    state = getattr(snapshot, "state", None)
    while isinstance(state, list) and state:
        state = state[0]
    if hasattr(state, "value"):
        return state.value
    if isinstance(state, dict):
        return state.get("value") or state.get("name") or state.get("state")
    if isinstance(state, str):
        return state
    return None


def _build_activity_bundle(state: dict[str, object], *, paused: bool = False):
    @activity.defn(name="fetch_monitored_policy")
    async def fetch_monitored_policy(monitored_id: str) -> dict[str, object]:
        state["policy_calls"] += 1
        next_check_at = datetime.now(timezone.utc) + timedelta(seconds=1)
        return PolicyActivityOutput(
            interval_seconds=1,
            next_check_at=next_check_at.isoformat(),
            paused=paused,
            stability_score=state["policy_calls"],
            scheduling_reason="integration-policy",
        ).__dict__

    @activity.defn(name="dispatch_collection")
    async def dispatch_collection(
        monitored_id: str,
        user_id: str,
        correlation_id: str,
        trace_id: str,
        force_compare: bool = False,
    ) -> DispatchActivityOutput:
        state["dispatch_calls"].append(
            {
                "monitored_id": monitored_id,
                "user_id": user_id,
                "correlation_id": correlation_id,
                "trace_id": trace_id,
                "force_compare": force_compare,
            }
        )
        return DispatchActivityOutput(success=True, task_id="task-1")

    @activity.defn(name="query_collection_status")
    async def query_collection_status(
        monitored_id: str,
        correlation_id: str,
    ) -> QueryStatusOutput:
        state["status_calls"].append(
            {
                "monitored_id": monitored_id,
                "correlation_id": correlation_id,
            }
        )
        return QueryStatusOutput(completed=True)

    @activity.defn(name="persist_workflow_snapshot")
    async def persist_workflow_snapshot(snapshot: WorkflowSnapshot) -> None:
        normalized_snapshot = snapshot
        while isinstance(normalized_snapshot, list) and normalized_snapshot:
            normalized_snapshot = normalized_snapshot[0]
        if isinstance(normalized_snapshot, dict):
            snapshot_state = normalized_snapshot.get("state", WorkflowState.Active)
            if isinstance(snapshot_state, str):
                snapshot_state = WorkflowState(snapshot_state)

            next_run_at = normalized_snapshot.get("next_run_at")
            if isinstance(next_run_at, str):
                next_run_at = datetime.fromisoformat(next_run_at)

            last_run_at = normalized_snapshot.get("last_run_at")
            if isinstance(last_run_at, str):
                last_run_at = datetime.fromisoformat(last_run_at)

            normalized_snapshot = WorkflowSnapshot(
                state=snapshot_state,
                next_run_at=next_run_at,
                last_run_at=last_run_at,
                last_error=normalized_snapshot.get("last_error"),
                attempt_count=normalized_snapshot.get("attempt_count", 0),
                monitored_id=normalized_snapshot.get("monitored_id", ""),
            )

        state["snapshots"].append(normalized_snapshot)

    @activity.defn(name="cleanup_workflow_state")
    async def cleanup_workflow_state(monitored_id: str) -> None:
        state["cleanup_calls"].append(monitored_id)

    return [
        fetch_monitored_policy,
        dispatch_collection,
        query_collection_status,
        persist_workflow_snapshot,
        cleanup_workflow_state,
    ]


@pytest.mark.asyncio
async def test_temporal_workflow_execution_advances_cycle_and_preserves_correlation(
    temporal_test_environment,
    workflow_input,
    wait_until,
) -> None:
    state = {
        "policy_calls": 0,
        "dispatch_calls": [],
        "status_calls": [],
        "snapshots": [],
        "cleanup_calls": [],
    }
    activities = _build_activity_bundle(state)

    async with Worker(
        temporal_test_environment.client,
        task_queue="market-orchestrator-integration",
        workflows=[MonitoredProductWorkflow],
        activities=activities,
    ):
        handle = await temporal_test_environment.client.start_workflow(
            "MonitoredProductWorkflow",
            workflow_input,
            id=f"monitored:{workflow_input.monitored_id}",
            task_queue="market-orchestrator-integration",
        )

        await wait_until(lambda: len(state["status_calls"]) >= 1)
        await handle.signal("delete")
        await handle.result()

    assert state["dispatch_calls"]
    assert state["status_calls"]
    assert state["cleanup_calls"] == [workflow_input.monitored_id]
    assert state["dispatch_calls"][0]["correlation_id"]
    assert all(
        item["monitored_id"] == workflow_input.monitored_id
        for item in state["status_calls"]
    )
    assert state["snapshots"]
    assert any(item.monitored_id == workflow_input.monitored_id for item in state["snapshots"])


@pytest.mark.asyncio
async def test_temporal_client_contract_operates_against_real_worker(
    temporal_test_environment,
    workflow_input,
    worker_test_config,
    wait_until,
    monkeypatch,
) -> None:
    state = {
        "policy_calls": 0,
        "dispatch_calls": [],
        "status_calls": [],
        "snapshots": [],
        "cleanup_calls": [],
    }
    activities = _build_activity_bundle(state)
    client = TemporalOrchestrationClient()

    async def fake_connect(target: str, namespace: str):
        assert namespace == worker_test_config.TEMPORAL_NAMESPACE
        return temporal_test_environment.client

    monkeypatch.setattr(
        "shared.clients.temporal.orchestrator_client.Client.connect",
        fake_connect,
    )
    monkeypatch.setattr(
        "shared.clients.temporal.orchestrator_client._config",
        lambda: worker_test_config,
    )

    async with Worker(
        temporal_test_environment.client,
        task_queue=worker_test_config.TEMPORAL_TASK_QUEUE,
        workflows=[MonitoredProductWorkflow],
        activities=activities,
    ):
        started = await client.signal_with_start(workflow_input)
        assert started is True

        await wait_until(lambda: len(state["dispatch_calls"]) >= 1)

        snapshot = await client.query(workflow_input.monitored_id)
        assert isinstance(snapshot, WorkflowSnapshot)

        resumed = await client.signal(
            "resume",
            workflow_input.monitored_id,
            ResumeSignalPayload(immediate_collect=False),
        )
        assert resumed is True

        deleted = await client.signal("delete", workflow_input.monitored_id)
        assert deleted is True

        handle = temporal_test_environment.client.get_workflow_handle(
            f"monitored:{workflow_input.monitored_id}"
        )
        await handle.result()

        connected = await client.probe_connectivity()
        assert connected is True

    assert state["cleanup_calls"] == [workflow_input.monitored_id]


@pytest.mark.asyncio
async def test_temporal_client_reconnects_after_transient_connect_failure_against_real_worker(
    temporal_test_environment,
    workflow_input,
    worker_test_config,
    wait_until,
    monkeypatch,
) -> None:
    state = {
        "policy_calls": 0,
        "dispatch_calls": [],
        "status_calls": [],
        "snapshots": [],
        "cleanup_calls": [],
    }
    activities = _build_activity_bundle(state)
    client = TemporalOrchestrationClient()
    connect_attempts = {"count": 0}

    async def fake_connect(target: str, namespace: str):
        connect_attempts["count"] += 1
        assert namespace == worker_test_config.TEMPORAL_NAMESPACE
        if connect_attempts["count"] == 1:
            raise RuntimeError("temporal temporarily unavailable")
        return temporal_test_environment.client

    sleep_calls: list[int | float] = []

    monkeypatch.setattr(
        "shared.clients.temporal.orchestrator_client.Client.connect",
        fake_connect,
    )
    monkeypatch.setattr(
        "shared.clients.temporal.orchestrator_client._config",
        lambda: worker_test_config,
    )

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(
        "shared.clients.temporal.orchestrator_client.asyncio.sleep",
        fake_sleep,
    )

    async with Worker(
        temporal_test_environment.client,
        task_queue=worker_test_config.TEMPORAL_TASK_QUEUE,
        workflows=[MonitoredProductWorkflow],
        activities=activities,
    ):
        started = await client.signal_with_start(workflow_input)
        assert started is True

        handle = temporal_test_environment.client.get_workflow_handle(
            f"monitored:{workflow_input.monitored_id}"
        )
        await wait_until(lambda: connect_attempts["count"] == 2)

        await handle.signal("delete")
        await handle.result()

    assert connect_attempts["count"] == 2
    assert sleep_calls == [1]
    assert state["cleanup_calls"] == [workflow_input.monitored_id]
