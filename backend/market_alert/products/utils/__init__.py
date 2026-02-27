""" Utilitários de domínio de produtos do serviço market_alert. 

Reúne helpers reutilizáveis em serviços, CRUD e domínio sem exigir importação
por caminho interno de cada arquivo utilitário.
"""

from market_alert.products.utils.interval_calculator_products import (
    RetryContext,
    SchedulingDecision,
    calculate_next_check_at,
    calculate_next_interval,
    calculate_schedule,
    calculate_stability_score,
)
from market_alert.products.utils.name_derivation import (
    derive_name_from_url,
    prepare_effective_name,
    should_replace_with_scraped,
)
from market_alert.products.utils.price_decimal import (
    different_price,
    different_prices,
    to_decimal,
)
from market_alert.products.utils.price_utils import (
    normalize_scraped_price,
    should_create_price_history,
)
from market_alert.products.utils.product_stats_formatter import (
    StabilityLevel,
    format_last_collected_at,
    format_next_check_at,
    format_stability_level,
    get_product_stats,
)

__all__ = [
    "RetryContext",
    "SchedulingDecision",
    "calculate_stability_score",
    "calculate_next_interval",
    "calculate_schedule",
    "calculate_next_check_at",
    "derive_name_from_url",
    "prepare_effective_name",
    "should_replace_with_scraped",
    "to_decimal",
    "different_prices",
    "different_price",
    "normalize_scraped_price",
    "should_create_price_history",
    "StabilityLevel",
    "format_stability_level",
    "format_next_check_at",
    "format_last_collected_at",
    "get_product_stats",
]
