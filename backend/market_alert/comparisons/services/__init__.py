""" Facade de serviços do domínio de comparações

Este módulo expõe os casos de uso públicos para consumo por rotas e
integrações internas, evitando acoplamento com arquivos concretos.
"""

from market_alert.comparisons.services.services_comparison import (
    get_comparison_detail_for_user,
    get_comparison_summary_for_user,
    get_paginated_comparisons_for_user,
    persist_rebuilt_summary_if_needed,
    rebuild_summary_from_current_state,
    run_price_comparison,
    summarize_comparison,
)

__all__ = [
    "get_comparison_detail_for_user",
    "get_comparison_summary_for_user",
    "get_paginated_comparisons_for_user",
    "persist_rebuilt_summary_if_needed",
    "rebuild_summary_from_current_state",
    "run_price_comparison",
    "summarize_comparison",
]