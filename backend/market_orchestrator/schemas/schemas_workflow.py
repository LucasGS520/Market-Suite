""" Schema de entrada do workflow e reexportações transitórias """
from __future__ import annotations

from dataclasses import dataclass, field

from market_orchestrator.enums.enums_workflow import WorkflowState
from market_orchestrator.schemas.schemas_policy import CollectionPolicy
from market_orchestrator.schemas.schemas_signals import (
    CompetitorChangedPayload,
    ResumeSignalPayload,
    UpdatePolicySignalPayload,
)
from market_orchestrator.schemas.schemas_snapshot import (
    CollectionStatusResult,
    WorkflowSnapshot,
)


# ---------------------------------------------------------------------------
# Payload de entrada para início do workflow e Continue-As-New
# ---------------------------------------------------------------------------

@dataclass
class WorkflowInput:
    monitored_id: str  #UUID serializado
    user_id: str       #UUID serializado
    policy: CollectionPolicy = field(default_factory=CollectionPolicy)
    bootstrap_flags: dict = field(default_factory=dict)
    #Flags possíveis: {"is_reconciliation": True, "resume_state": "WaitingTimer", ...}


__all__ = [
    "WorkflowState",
    "CollectionPolicy",
    "WorkflowInput",
    "ResumeSignalPayload",
    "UpdatePolicySignalPayload",
    "CompetitorChangedPayload",
    "WorkflowSnapshot",
    "CollectionStatusResult",
]
