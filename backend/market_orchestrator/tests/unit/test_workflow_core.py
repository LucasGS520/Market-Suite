from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

import market_orchestrator.workflow as workflow_module
from market_orchestrator.enums.enums_workflow import WorkflowState
from market_orchestrator.workflow import MonitoredProductWorkflow
from shared.schemas.shared_schemas_orchestrator import (
    CollectionPolicy,
    DispatchActivityOutput,
    PolicyActivityOutput,
    QueryStatusOutput,
    ResumeSignalPayload,
    WorkflowInput,
)


pytestmark = pytest.mark.unit


class _WorkflowInfoStub:
    def __init__(self, history_length: int) -> None:
        self._history_length = history_length

    def get_current_history_length(self) -> int:
        return self._history_length


@pytest.mark.asyncio
async def test_run_restores_resume_state_before_entering_loop(workflow_policy) -> None:
    instance = MonitoredProductWorkflow()
    instance._run_loop = AsyncMock()

    await instance.run(
        WorkflowInput(
            monitored_id="monitored-1",
            user_id="user-1",
            policy=workflow_policy,
            bootstrap_flags={"resume_state": WorkflowState.Paused.value},
        )
    )

    assert instance._state is WorkflowState.Paused
    instance._run_loop.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_falls_back_to_waiting_timer_for_invalid_resume_state(
    workflow_policy,
) -> None:
    instance = MonitoredProductWorkflow()
    instance._run_loop = AsyncMock()

    await instance.run(
        WorkflowInput(
            monitored_id="monitored-1",
            user_id="user-1",
            policy=workflow_policy,
            bootstrap_flags={"resume_state": "not-a-real-state"},
        )
    )

    assert instance._state is WorkflowState.WaitingTimer
    instance._run_loop.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_loop_continues_as_new_when_history_limit_is_reached(
    workflow_instance,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        workflow_module.workflow,
        "info",
        lambda: _WorkflowInfoStub(workflow_module._HISTORY_LENGTH_LIMIT),
    )
    workflow_instance._continue_as_new = AsyncMock()

    await workflow_instance._run_loop()

    workflow_instance._continue_as_new.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_waiting_timer_applies_pending_policy_update_and_dispatches(
    workflow_instance,
    workflow_now,
    monkeypatch,
) -> None:
    updated_policy = CollectionPolicy(
        interval_seconds=15,
        backoff_max_attempts=9,
        backoff_base_seconds=7,
        stability_score=11,
        scheduling_reason="signal-update",
    )
    next_check_at = (workflow_now + timedelta(seconds=120)).isoformat()

    async def fake_execute_activity(*args, **kwargs):
        return PolicyActivityOutput(
            interval_seconds=90,
            next_check_at=next_check_at,
            paused=False,
            stability_score=5,
            scheduling_reason="db-policy",
        ).__dict__

    monkeypatch.setattr(workflow_module.workflow, "execute_activity", fake_execute_activity)
    monkeypatch.setattr(workflow_module.workflow, "now", lambda: workflow_now)
    workflow_instance._policy_update = updated_policy
    workflow_instance._persist_snapshot = AsyncMock()
    workflow_instance._sleep_preemptible = AsyncMock(return_value=False)

    await workflow_instance._handle_waiting_timer()

    assert workflow_instance._policy == updated_policy
    assert workflow_instance._policy_update is None
    assert workflow_instance._next_run_at == workflow_now + timedelta(seconds=120)
    assert workflow_instance._state is WorkflowState.Dispatching
    workflow_instance._persist_snapshot.assert_awaited_once()
    workflow_instance._sleep_preemptible.assert_awaited_once_with(120.0)


@pytest.mark.asyncio
async def test_handle_waiting_timer_transitions_to_paused_when_policy_marks_paused(
    workflow_instance,
    monkeypatch,
) -> None:
    async def fake_execute_activity(*args, **kwargs):
        return PolicyActivityOutput(paused=True).__dict__

    monkeypatch.setattr(workflow_module.workflow, "execute_activity", fake_execute_activity)

    await workflow_instance._handle_waiting_timer()

    assert workflow_instance._state is WorkflowState.Paused


@pytest.mark.asyncio
async def test_handle_dispatching_stores_correlation_and_enters_waiting_result(
    workflow_instance,
    workflow_now,
    monkeypatch,
) -> None:
    correlation_uuid = UUID("11111111-1111-1111-1111-111111111111")
    trace_uuid = UUID("22222222-2222-2222-2222-222222222222")
    uuids = iter([correlation_uuid, trace_uuid])

    async def fake_execute_activity(*args, **kwargs):
        return DispatchActivityOutput(success=True, task_id="task-1")

    monkeypatch.setattr(workflow_module.workflow, "execute_activity", fake_execute_activity)
    monkeypatch.setattr(workflow_module.workflow, "uuid4", lambda: next(uuids))
    monkeypatch.setattr(workflow_module.workflow, "now", lambda: workflow_now)

    await workflow_instance._handle_dispatching()

    assert workflow_instance._state is WorkflowState.WaitingResult
    assert workflow_instance._current_correlation_id == str(correlation_uuid)
    assert workflow_instance._last_run_at == workflow_now
    assert workflow_instance._last_error is None


@pytest.mark.asyncio
async def test_handle_dispatching_moves_to_backoff_on_activity_error(
    workflow_instance,
    monkeypatch,
) -> None:
    async def fake_execute_activity(*args, **kwargs):
        raise RuntimeError("dispatch failed")

    monkeypatch.setattr(workflow_module, "ActivityError", RuntimeError)
    monkeypatch.setattr(workflow_module.workflow, "execute_activity", fake_execute_activity)
    monkeypatch.setattr(workflow_module.workflow, "uuid4", lambda: UUID(int=1))

    await workflow_instance._handle_dispatching()

    assert workflow_instance._state is WorkflowState.Backoff
    assert workflow_instance._last_error == "dispatch failed"


@pytest.mark.asyncio
async def test_handle_waiting_result_resets_attempts_when_collection_completes(
    workflow_instance,
    workflow_now,
    monkeypatch,
) -> None:
    now_values = iter([workflow_now, workflow_now])

    async def fake_execute_activity(*args, **kwargs):
        return QueryStatusOutput(completed=True)

    monkeypatch.setattr(workflow_module.workflow, "execute_activity", fake_execute_activity)
    monkeypatch.setattr(workflow_module.workflow, "now", lambda: next(now_values))
    workflow_instance._attempt_count = 2
    workflow_instance._current_correlation_id = "corr-1"
    workflow_instance._persist_snapshot = AsyncMock()

    await workflow_instance._handle_waiting_result()

    assert workflow_instance._attempt_count == 0
    assert workflow_instance._state is WorkflowState.WaitingTimer
    workflow_instance._persist_snapshot.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_waiting_result_times_out_into_backoff(
    workflow_instance,
    workflow_now,
    monkeypatch,
) -> None:
    now_values = iter(
        [
            workflow_now,
            workflow_now,
            workflow_now + timedelta(seconds=workflow_module._COLLECTION_RESULT_TIMEOUT_SECONDS + 1),
        ]
    )
    sleep_mock = AsyncMock()

    async def fake_execute_activity(*args, **kwargs):
        return QueryStatusOutput(completed=False)

    monkeypatch.setattr(workflow_module.workflow, "execute_activity", fake_execute_activity)
    monkeypatch.setattr(workflow_module.workflow, "now", lambda: next(now_values))
    monkeypatch.setattr(workflow_module.workflow, "sleep", sleep_mock)
    workflow_instance._current_correlation_id = "corr-1"

    await workflow_instance._handle_waiting_result()

    assert workflow_instance._state is WorkflowState.Backoff
    assert workflow_instance._last_error == "collection_result_timeout"
    sleep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_backoff_transitions_to_failed_terminal_at_limit(
    workflow_instance,
) -> None:
    workflow_instance._attempt_count = workflow_instance._policy.backoff_max_attempts - 1

    await workflow_instance._handle_backoff()

    assert workflow_instance._attempt_count == workflow_instance._policy.backoff_max_attempts
    assert workflow_instance._state is WorkflowState.FailedTerminal


@pytest.mark.asyncio
async def test_handle_backoff_sleeps_and_retries_before_limit(
    workflow_instance,
    monkeypatch,
) -> None:
    sleep_mock = AsyncMock()
    monkeypatch.setattr(workflow_module.workflow, "sleep", sleep_mock)

    await workflow_instance._handle_backoff()

    sleep_mock.assert_awaited_once_with(
        timedelta(seconds=workflow_instance._policy.backoff_base_seconds)
    )
    assert workflow_instance._attempt_count == 1
    assert workflow_instance._state is WorkflowState.Dispatching


@pytest.mark.asyncio
async def test_handle_paused_resumes_into_dispatching_when_immediate_collect(
    workflow_instance,
    monkeypatch,
) -> None:
    workflow_instance._resume_payload = ResumeSignalPayload(immediate_collect=True)
    workflow_instance._attempt_count = 4
    workflow_instance._persist_snapshot = AsyncMock()
    monkeypatch.setattr(
        workflow_module.workflow,
        "wait_condition",
        AsyncMock(return_value=None),
    )

    await workflow_instance._handle_paused()

    assert workflow_instance._attempt_count == 0
    assert workflow_instance._resume_payload is None
    assert workflow_instance._state is WorkflowState.Dispatching
    workflow_instance._persist_snapshot.assert_awaited_once()


@pytest.mark.asyncio
async def test_continue_as_new_preserves_state_and_attempt_count(
    workflow_instance,
    monkeypatch,
) -> None:
    captured_input: list[WorkflowInput] = []

    def fake_continue_as_new(new_input: WorkflowInput) -> None:
        captured_input.append(new_input)

    monkeypatch.setattr(workflow_module.workflow, "continue_as_new", fake_continue_as_new)
    workflow_instance._state = WorkflowState.Backoff
    workflow_instance._attempt_count = 2

    await workflow_instance._continue_as_new()

    assert captured_input
    assert captured_input[0].bootstrap_flags == {
        "resume_state": WorkflowState.Backoff.value,
        "attempt_count": 2,
    }
    assert captured_input[0].policy == workflow_instance._policy
