"""Schemas de input/output para o workflow Temporal e seus signals/queries."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID


# ---------------------------------------------------------------------------
# Estado da máquina de estados do workflow
# ---------------------------------------------------------------------------

class WorkflowState(str, enum.Enum):
    Active = "Active"
    WaitingTimer = "WaitingTimer"
    Dispatching = "Dispatching"
    WaitingResult = "WaitingResult"
    Backoff = "Backoff"
    Paused = "Paused"
    FailedTerminal = "FailedTerminal"
    CompletedDeleted = "CompletedDeleted"


# ---------------------------------------------------------------------------
# Política de coleta (intervalo mínimo/máximo em segundos)
# ---------------------------------------------------------------------------

@dataclass
class CollectionPolicy:
    interval_seconds: int = 3600          # intervalo base de rechecagem
    backoff_max_attempts: int = 5
    backoff_base_seconds: int = 60


# ---------------------------------------------------------------------------
# Input do workflow (entrada inicial e após Continue-As-New)
# ---------------------------------------------------------------------------

@dataclass
class WorkflowInput:
    monitored_id: str                     # UUID serializado como str
    user_id: str                          # UUID serializado como str
    policy: CollectionPolicy = field(default_factory=CollectionPolicy)
    bootstrap_flags: dict = field(default_factory=dict)
    # Possíveis flags: {"is_reconciliation": True, "resume_state": "WaitingTimer", ...}


# ---------------------------------------------------------------------------
# Payloads de signals
# ---------------------------------------------------------------------------

@dataclass
class ResumeSignalPayload:
    immediate_collect: bool = False


@dataclass
class UpdatePolicySignalPayload:
    policy: CollectionPolicy = field(default_factory=CollectionPolicy)


@dataclass
class CompetitorChangedPayload:
    event: Literal["added", "removed"] = "added"
    competitor_id: str = ""               # UUID serializado como str


# ---------------------------------------------------------------------------
# Snapshot retornado pela query get_state
# ---------------------------------------------------------------------------

@dataclass
class WorkflowSnapshot:
    state: WorkflowState = WorkflowState.Active
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_error: str | None = None
    attempt_count: int = 0
    monitored_id: str = ""


# ---------------------------------------------------------------------------
# Resultado da activity query_collection_status
# ---------------------------------------------------------------------------

@dataclass
class CollectionStatusResult:
    completed: bool = False
    last_error: str | None = None
