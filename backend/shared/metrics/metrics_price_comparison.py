""" Métricas para rotinas de comparação de preços """

from prometheus_client import Counter, Histogram

PRICE_COMPARISONS_TOTAL = Counter(
    "price_comparisons_total",
    "Total de execuções de comparação de preços",
    ["status"],
)

PRICE_COMPARISON_DURATION_SECONDS = Histogram(
    "price_comparison_duration_seconds",
    "Tempo de execução da comparação de preços (segundos)",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0],
)

PRICE_ALERTS_TOTAL = Counter(
    "price_alerts_total",
    "Total de alertas de preço gerados",
)

PRICE_COMPARISON_TASK_LATENCY_SECONDS = Histogram(
    "price_comparison_task_latency_seconds",
    "Tempo total da task Celery de comparação de preços",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10],
)

__all__ = [
    "PRICE_COMPARISONS_TOTAL",
    "PRICE_COMPARISON_DURATION_SECONDS",
    "PRICE_ALERTS_TOTAL",
    "PRICE_COMPARISON_TASK_LATENCY_SECONDS",
]
