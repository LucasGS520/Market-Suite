"""Cálculo de estabilidade para produtos monitorados.

Re-exporta a implementação canônica de interval_calculator_products para
centralizar imports na camada de domínio. A lógica de cálculo permanece em
interval_calculator_products para preservar compatibilidade com código existente.

Novo código deve importar daqui; código legado continua funcionando com
o import direto de interval_calculator_products.
"""

from market_alert.utils.interval_calculator_products import (
    STABILITY_STABLE,
    STABILITY_UNSTABLE,
    STABILITY_VERY_STABLE,
    calculate_stability_score,
)

__all__ = [
    "STABILITY_UNSTABLE",
    "STABILITY_STABLE",
    "STABILITY_VERY_STABLE",
    "calculate_stability_score",
]
