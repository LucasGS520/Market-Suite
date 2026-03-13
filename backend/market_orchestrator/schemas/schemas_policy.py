""" Schemas de política para o workflow do market_orchestrator """
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CollectionPolicy:
    interval_seconds: int = 3600 #Intervalo base de nova checagem
    backoff_max_attempts: int = 5
    backoff_base_seconds: int = 60


__all__ = ["CollectionPolicy"]
