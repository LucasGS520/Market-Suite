from __future__ import annotations

from market_orchestrator.enums.enums_workflow import WorkflowState
from market_orchestrator.schemas.schemas_snapshot import WorkflowSnapshot
from market_orchestrator.schemas.schemas_workflow import (
    CollectionPolicy,
    CompetitorChangedPayload,
    ResumeSignalPayload,
    UpdatePolicySignalPayload,
    WorkflowInput,
    WorkflowSnapshot as ReexportedWorkflowSnapshot,
    WorkflowState as ReexportedWorkflowState,
)


def test_workflow_state_enum_values_remain_stable() -> None:
    assert [state.value for state in WorkflowState] == [
        "Active",
        "WaitingTimer",
        "Dispatching",
        "WaitingResult",
        "Backoff",
        "Paused",
        "FailedTerminal",
        "CompletedDeleted",
    ]


def test_workflow_snapshot_defaults_are_safe_for_empty_query() -> None:
    snapshot = WorkflowSnapshot()

    assert snapshot.state is WorkflowState.Active
    assert snapshot.next_run_at is None
    assert snapshot.last_run_at is None
    assert snapshot.last_error is None
    assert snapshot.attempt_count == 0
    assert snapshot.monitored_id == ""


def test_workflow_schema_reexports_keep_backward_compatible_contracts() -> None:
    assert ReexportedWorkflowState is WorkflowState
    assert ReexportedWorkflowSnapshot is WorkflowSnapshot


def test_workflow_input_uses_isolated_bootstrap_flags() -> None:
    first = WorkflowInput(monitored_id="m1", user_id="u1")
    second = WorkflowInput(monitored_id="m2", user_id="u2")

    first.bootstrap_flags["resume_state"] = WorkflowState.Paused.value

    assert second.bootstrap_flags == {}


def test_signal_payload_defaults_are_predictable() -> None:
    resume_payload = ResumeSignalPayload()
    update_payload = UpdatePolicySignalPayload()
    competitor_payload = CompetitorChangedPayload()

    assert resume_payload.immediate_collect is False
    assert isinstance(update_payload.policy, CollectionPolicy)
    assert competitor_payload.event == "added"
    assert competitor_payload.competitor_id == ""
