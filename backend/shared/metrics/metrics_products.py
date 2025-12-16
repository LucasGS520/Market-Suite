"""Métricas específicas para fluxos de produtos e concorrentes."""

from prometheus_client import Counter

PENDING_COMPETITOR_CREATED_TOTAL = Counter(
    "pending_competitor_created_total",
    "Total de concorrentes criados com status pendente aguardando scraping",
)

PRICE_HISTORY_CREATED_TOTAL = Counter(
    "price_history_created_total",
    "Total de registros de histórico de preço persistidos por tipo de dono",
    labelnames=["owner"],
)

__all__ = ["PENDING_COMPETITOR_CREATED_TOTAL", "PRICE_HISTORY_CREATED_TOTAL"]
