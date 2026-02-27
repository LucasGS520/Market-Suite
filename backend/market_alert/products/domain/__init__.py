""" Contratos e tipos de domínio de produtos 

Expõe contratos e regras centrais de ciclo de vida para padronizar os imports
de quem consome a feature fora da camada de domínio.
"""

from market_alert.products.domain.contracts import (
    ActivationLifecycleContract,
    CollectionIntervalContract,
    LifecycleStatsContract,
    ProductLifecycleContract,
)
from market_alert.products.domain.product_lifecycle import (
    compute_next_check_at,
    resolve_scheduling_event,
    update_competitor_price_change_tracking,
    update_price_change_tracking,
    validate_status_transition,
)
from market_alert.products.domain.stability import (
    STABILITY_STABLE,
    STABILITY_UNSTABLE,
    STABILITY_VERY_STABLE,
    calculate_stability_score,
)

__all__ = [
    "ActivationLifecycleContract",
    "CollectionIntervalContract",
    "LifecycleStatsContract",
    "ProductLifecycleContract",
    "STABILITY_UNSTABLE",
    "STABILITY_STABLE",
    "STABILITY_VERY_STABLE",
    "calculate_stability_score",
    "resolve_scheduling_event",
    "compute_next_check_at",
    "validate_status_transition",
    "update_price_change_tracking",
    "update_competitor_price_change_tracking",
]