from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

import market_orchestrator.workflow as workflow_module
from market_orchestrator.enums.enums_workflow import WorkflowState
from shared.schemas.shared_schemas_orchestrator import (
    CollectionPolicy,
    CompetitorChangedPayload,
    ResumeSignalPayload,
    UpdatePolicySignalPayload,
)


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_signal_pause_moves_workflow_to_paused(workflow_instance) -> None:
    await workflow_instance.signal_pause()

    assert workflow_instance._signal_count == 1
    assert workflow_instance._pause_requested is True
    assert workflow_instance._state is WorkflowState.Paused


@pytest.mark.asyncio
async def test_signal_resume_stores_payload_and_clears_pause(workflow_instance) -> None:
    payload = ResumeSignalPayload(immediate_collect=True)
    workflow_instance._pause_requested = True

    await workflow_instance.signal_resume(payload)

    assert workflow_instance._signal_count == 1
    assert workflow_instance._pause_requested is False
    assert workflow_instance._resume_payload == payload


@pytest.mark.asyncio
async def test_signal_delete_marks_workflow_for_cleanup(workflow_instance) -> None:
    await workflow_instance.signal_delete()

    assert workflow_instance._signal_count == 1
    assert workflow_instance._delete_requested is True


@pytest.mark.asyncio
async def test_signal_competitor_changed_only_preempts_waiting_timer(workflow_instance) -> None:
    payload = CompetitorChangedPayload(event="added", competitor_id="comp-1")

    workflow_instance._state = WorkflowState.Dispatching
    await workflow_instance.signal_competitor_changed(payload)
    assert workflow_instance._competitor_changed is False

    workflow_instance._state = WorkflowState.WaitingTimer
    await workflow_instance.signal_competitor_changed(payload)
    assert workflow_instance._signal_count == 2
    assert workflow_instance._competitor_changed is True


@pytest.mark.asyncio
async def test_signal_update_policy_stores_override_for_next_cycle(workflow_instance) -> None:
    payload = UpdatePolicySignalPayload(
        policy=CollectionPolicy(
            interval_seconds=15,
            backoff_max_attempts=8,
            backoff_base_seconds=9,
            stability_score=7,
            scheduling_reason="manual-update",
        )
    )

    await workflow_instance.signal_update_policy(payload)

    assert workflow_instance._signal_count == 1
    assert workflow_instance._policy_update == payload.policy


def test_query_get_state_exposes_current_snapshot(workflow_instance, workflow_now) -> None:
    workflow_instance._state = WorkflowState.Backoff
    workflow_instance._next_run_at = workflow_now
    workflow_instance._last_run_at = workflow_now
    workflow_instance._last_error = "boom"
    workflow_instance._attempt_count = 3

    snapshot = workflow_instance.query_get_state()

    assert snapshot.state is WorkflowState.Backoff
    assert snapshot.next_run_at == workflow_now
    assert snapshot.last_run_at == workflow_now
    assert snapshot.last_error == "boom"
    assert snapshot.attempt_count == 3
    assert snapshot.monitored_id == "monitored-1"


@pytest.mark.asyncio
async def test_sleep_preemptible_preempts_on_competitor_change(
    workflow_instance,
    monkeypatch,
) -> None:
    workflow_instance._competitor_changed = True
    monkeypatch.setattr(
        workflow_module.workflow,
        "wait_condition",
        AsyncMock(return_value=None),
    )

    preempted = await workflow_instance._sleep_preemptible(30)

    assert preempted is True
    assert workflow_instance._competitor_changed is False
    assert workflow_instance._state is WorkflowState.Dispatching


@pytest.mark.asyncio
async def test_sleep_preemptible_ignores_resume_signal_while_already_active(
    workflow_instance,
    monkeypatch,
) -> None:
    workflow_instance._resume_payload = ResumeSignalPayload(immediate_collect=True)
    monkeypatch.setattr(
        workflow_module.workflow,
        "wait_condition",
        AsyncMock(return_value=None),
    )

    preempted = await workflow_instance._sleep_preemptible(30)

    assert preempted is False
    assert workflow_instance._resume_payload is None


@pytest.mark.asyncio
async def test_sleep_preemptible_returns_false_when_timer_expires(
    workflow_instance,
    monkeypatch,
) -> None:
    async def fake_wait_condition(*args, **kwargs):
        raise asyncio.TimeoutError

    monkeypatch.setattr(workflow_module.workflow, "wait_condition", fake_wait_condition)

    preempted = await workflow_instance._sleep_preemptible(30)

    assert preempted is False


@pytest.mark.asyncio
async def test_do_delete_cleans_up_and_marks_completed_deleted(
    workflow_instance,
    monkeypatch,
) -> None:
    cleanup_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(workflow_module.workflow, "execute_activity", cleanup_mock)
    workflow_instance._delete_requested = True

    await workflow_instance._do_delete()

    assert workflow_instance._delete_requested is False
    assert workflow_instance._state is WorkflowState.CompletedDeleted
    cleanup_mock.assert_awaited_once()
