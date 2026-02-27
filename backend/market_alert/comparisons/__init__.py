""" Facade pública da feature de comparações de preços.

A feature expõe somente interfaces estáveis para rotas e casos de uso,
evita dependência direta em submódulos internos.
"""

from market_alert.comparisons.routes import comparisons_router
from market_alert.comparisons.services import (
    get_comparison_detail_for_user,
    get_comparison_summary_for_user,
    get_paginated_comparisons_for_user,
    persist_rebuilt_summary_if_needed,
    rebuild_summary_from_current_state,
    run_price_comparison,
    summarize_comparison,
)

__all__ = [
    "comparisons_router",
    "get_paginated_comparisons_for_user",
    "get_comparison_summary_for_user",
    "get_comparison_detail_for_user",
    "persist_rebuilt_summary_if_needed",
    "rebuild_summary_from_current_state",
    "run_price_comparison",
    "summarize_comparison",
]
