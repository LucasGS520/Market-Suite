""" Enums de workflow para o market_orchestrator """
from __future__ import annotations

import enum


class WorkflowState(str, enum.Enum):
    Active = "Active"
    WaitingTimer = "WaitingTimer"
    Dispatching = "Dispatching"
    WaitingResult = "WaitingResult"
    Backoff = "Backoff"
    Paused = "Paused"
    FailedTerminal = "FailedTerminal"
    CompletedDeleted = "CompletedDeleted"


__all__ = ["WorkflowState"]
