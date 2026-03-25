""" Cálculo de estabilidade para produtos monitorados.

Re-exporta a implementação canônica de shared.scheduling para centralizar
imports na camada de domínio.

Novo código deve importar diretamente de shared.scheduling.
"""

from shared.scheduling import (
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
