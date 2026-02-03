"""Métricas específicas para fluxos de produtos e concorrentes."""

import os

# Importa métricas apropriadas baseado em ENABLE_METRICS
_ENABLE_METRICS = os.getenv("ENABLE_METRICS", "0") in {"1", "true", "True", "yes"}
if _ENABLE_METRICS:
    from prometheus_client import Counter
else:
    from shared.metrics_noop import Counter

MONITORED_PAUSED_TOTAL = Counter(
    "monitored_paused_total",
    "Total de produtos monitorados colocados em pausa",
)

MONITORED_RESUMED_TOTAL = Counter(
    "monitored_resumed_total",
    "Total de produtos monitorados reativados",
)

MONITORED_DELETED_TOTAL = Counter(
    "monitored_deleted_total",
    "Total de produtos monitorados removidos com segurança",
)

PENDING_COMPETITOR_CREATED_TOTAL = Counter(
    "pending_competitor_created_total",
    "Total de concorrentes criados com status pendente aguardando scraping",
)

COMPETITOR_DELETED_TOTAL = Counter(
    "competitor_deleted_total",
    "Total de concorrentes removidos com deleção definitiva",
)

COMPETITOR_DELETE_FAILURES_TOTAL = Counter(
    "competitor_delete_failures_total",
    "Falhas ao tentar remover concorrente de forma segura",
)

COMPETITOR_CHANGE_AFFECTED_STABILITY_TOTAL = Counter(
    "competitor_change_affected_stability_total",
    "Total de vezes em que mudanças de concorrentes reduziram a estabilidade do produto monitorado",
)

PRICE_HISTORY_CREATED_TOTAL = Counter(
    "price_history_created_total",
    "Total de registros de histórico de preço persistidos por tipo de dono",
    labelnames=["owner"],
)

PRICE_HISTORY_SKIPPED_UNAVAILABLE_TOTAL = Counter(
    "price_history_skipped_unavailable_total",
    "Total de históricos ignorados por indisponibilidade ou ausência de preço",
    labelnames=["owner"],
)

MONITORED_LISTED_WITHOUT_PRICE_TOTAL = Counter(
    "monitored_listed_without_price_total",
    "Listagens de monitorados entregues mesmo sem preço coletado",
)

__all__ = [
    "PENDING_COMPETITOR_CREATED_TOTAL",
    "PRICE_HISTORY_CREATED_TOTAL",
    "PRICE_HISTORY_SKIPPED_UNAVAILABLE_TOTAL",
    "MONITORED_LISTED_WITHOUT_PRICE_TOTAL",
    "MONITORED_PAUSED_TOTAL",
    "MONITORED_RESUMED_TOTAL",
    "MONITORED_DELETED_TOTAL",
    "COMPETITOR_DELETED_TOTAL",
    "COMPETITOR_DELETE_FAILURES_TOTAL",
    "COMPETITOR_CHANGE_AFFECTED_STABILITY_TOTAL",
]
