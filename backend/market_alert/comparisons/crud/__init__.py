"""Facade da camada de persistência de comparações.

Este módulo centraliza os pontos de entrada públicos do CRUD para evitar
acoplamento de consumidores com nomes de arquivos internos.
"""

from market_alert.comparisons.crud.crud_comparison import (
    create_price_comparison,
    create_price_comparison_summary,
    get_comparison_by_id,
    get_latest_comparisons,
    get_latest_comparisons_for_products,
    get_latest_summaries_for_products,
    get_latest_summary,
    paginate_comparisons,
    upsert_price_comparison_summary,
)

__all__ = [
    "create_price_comparison",
    "create_price_comparison_summary",
    "upsert_price_comparison_summary",
    "get_latest_comparisons",
    "paginate_comparisons",
    "get_comparison_by_id",
    "get_latest_summary",
    "get_latest_comparisons_for_products",
    "get_latest_summaries_for_products",
]
