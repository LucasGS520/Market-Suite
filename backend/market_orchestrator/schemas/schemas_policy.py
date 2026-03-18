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

@dataclass
class PolicyActivityResponse:
    """ Contrato tipado do retorno de fetch_monitored_policy.

    Permite que o workflow leia o resultado da activity sem raw dict access.
    Campos extras no dict de origem são ignorados por from_dict.
    """
    interval_seconds: int = 3600
    next_check_at: str | None = None #ISO 8601
    paused: bool = False
    stability_score: int = 0
    scheduling_reason: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyActivityResponse":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


__all__ = ["CollectionPolicy", "PolicyActivityResponse"]
