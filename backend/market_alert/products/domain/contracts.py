""" Contratos de domínio para lifecycle de produtos

Os contratos abaixo descrevem capacidades mínimas esperadas para fluxos de
ativação/desativação, cálculo de intervalos de coleta e exposição de métricas
agregadas de lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class CollectionIntervalContract:
    """ Representa a decisão de intervalo para a próxima coleta """

    next_check_at: datetime
    interval_minutes: int
    reason: str

@dataclass(frozen=True)
class LifecycleStatsContract:
    """ Representa estatísticas agregadas do ciclo de vida."""

    total_checks: int
    total_failures: int
    last_collected_at: datetime | None

@runtime_checkable
class ActivationLifecycleContract(Protocol):
    """ Capacidade de ativar ou desativar uma entidade monitorada."""

    def activate(self, product_id: UUID) -> None:
        """Ativa o monitoramento para o produto informado."""

    def deactivate(self, product_id: UUID) -> None:
        """Desativa o monitoramento para o produto informado."""

@runtime_checkable
class ProductLifecycleContract(Protocol):
    """ Contrato mínimo de lifecycle para monitorados e concorrentes."""

    def resolve_interval(self, product_id: UUID) -> CollectionIntervalContract:
        """Calcula o próximo intervalo de coleta para o produto."""

    def collect_stats(self, product_id: UUID) -> LifecycleStatsContract:
        """Retorna estatísticas consolidadas do lifecycle do produto."""
        