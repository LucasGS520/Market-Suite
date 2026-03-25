""" Schemas de snapshot e resultado de status para observabilidade do workflow """
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from market_orchestrator.enums.enums_workflow import WorkflowState


@dataclass
class WorkflowSnapshot:
    state: WorkflowState = WorkflowState.Active
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_error: str | None = None
    attempt_count: int = 0
    monitored_id: str = ""

@dataclass
class CollectionStatusResult:
    completed: bool = False
    last_error: str | None = None


__all__ = ["WorkflowSnapshot", "CollectionStatusResult"]
