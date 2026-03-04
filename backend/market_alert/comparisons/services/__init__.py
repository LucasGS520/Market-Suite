""" Facade estável da camada de serviços de comparações.

Este módulo centraliza e reexporta as funções públicas de
``services_comparison`` para oferecer um ponto único e estável de importação
para rotas HTTP, tarefas assíncronas e outros consumidores internos.
"""

from market_alert.comparisons.services.services_comparison import (
    ensure_user_can_view_monitored,
    get_comparison_detail_for_user,
    get_comparison_summary_for_user,
    get_paginated_comparisons_for_user,
    persist_rebuilt_summary_if_needed,
    rebuild_summary_from_current_state,
    run_price_comparison,
    summarize_comparison,
)

__all__ = [
    "ensure_user_can_view_monitored",
    "get_comparison_detail_for_user",
    "get_comparison_summary_for_user",
    "get_paginated_comparisons_for_user",
    "persist_rebuilt_summary_if_needed",
    "rebuild_summary_from_current_state",
    "run_price_comparison",
    "summarize_comparison",
]
