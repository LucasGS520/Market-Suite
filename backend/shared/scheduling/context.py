""" SchedulingContext — representação pura do estado de um monitorado para agendamento.

Substitui o modelo ORM MonitoredProduct como parâmetro das funções de agendamento,
eliminando a dependência de market_alert nos módulos de controle (market_orchestrator).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SchedulingContext:
    """ Dados de estado de um produto monitorado necessários para calcular o agendamento.

    Todos os campos datetime aceitam None e são normalizados para UTC internamente.
    O campo ``status`` é uma string pura (ex.: ``"pending"``, ``"active"``),
    desacoplado do enum ``MonitoredStatus`` de ``market_alert``.
    """
    status: str
    last_checked: datetime | None
    last_price_change_at: datetime | None
    group_collected_at: datetime | None
    last_scraped_at: datetime | None
    created_at: datetime | None
    next_check_at: datetime | None
    stability_score: int = 0


__all__ = ["SchedulingContext"]
