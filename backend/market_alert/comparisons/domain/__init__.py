""" Facade de regras de domínio para competitividade de preços.

Expõe apenas estruturas e funções estáveis para cálculo de
competitividade, mantendo detalhes internos encapsulados.
"""

from market_alert.comparisons.domain.price_competitiveness import (
    ComparisonSnapshot,
    CompetitivenessResult,
    CompetitivenessThresholds,
    calculate_competitiveness,
    determine_competitiveness_status,
)

__all__ = [
    "CompetitivenessThresholds",
    "ComparisonSnapshot",
    "CompetitivenessResult",
    "determine_competitiveness_status",
    "calculate_competitiveness",
]
