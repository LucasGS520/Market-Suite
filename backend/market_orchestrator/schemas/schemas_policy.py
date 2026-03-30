""" Schemas de política para o workflow do market_orchestrator """
from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass
class CollectionPolicy:
    interval_seconds: int = 3600 #Intervalo base de nova checagem
    backoff_max_attempts: int = 5
    backoff_base_seconds: int = 60
    stability_score: int = 0 #Score de estabilidade do produto (0=instável, 1=estável, 2=muito estável)
    scheduling_reason: str = "" #Motivo da decisão de agendamento para observabilidade

__all__ = ["CollectionPolicy"]
