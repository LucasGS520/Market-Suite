""" Schemas de payload de signals para o workflow do market_orchestrator """
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from market_orchestrator.schemas.schemas_policy import CollectionPolicy


@dataclass
class ResumeSignalPayload:
    immediate_collect: bool = False

@dataclass
class UpdatePolicySignalPayload:
    policy: CollectionPolicy = field(default_factory=CollectionPolicy)

@dataclass
class CompetitorChangedPayload:
    event: Literal["added", "removed"] = "added"
    competitor_id: str = "" #UUID serializado


__all__ = [
    "ResumeSignalPayload",
    "UpdatePolicySignalPayload",
    "CompetitorChangedPayload",
]
