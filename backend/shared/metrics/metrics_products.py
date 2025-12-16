"""Métricas específicas para fluxos de produtos e concorrentes."""

from prometheus_client import Counter

PENDING_COMPETITOR_CREATED_TOTAL = Counter(
    "pending_competitor_created_total",
    "Total de concorrentes criados com status pendente aguardando scraping",
)

__all__ = ["PENDING_COMPETITOR_CREATED_TOTAL"]