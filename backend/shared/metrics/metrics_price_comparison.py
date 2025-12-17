""" Métricas para rotinas de comparação de preços """

from prometheus_client import Counter, Histogram

PRICE_COMPARISONS_TOTAL = Counter(
    "price_comparisons_total",
    "Total de execuções de comparação de preços",
    ["status"],
)

MALFORMED_COMPARISON_PAYLOADS_TOTAL = Counter(
    "comparison_malformed_payloads_total",
    "Quantidade de payloads de comparação inválidos ou incompletos",
    ["stage"],
)

PRICE_COMPARISON_FAILURES_TOTAL = Counter(
    "comparison_failures_total",
    "Falhas ao calcular resumo de comparação de preços",
    ["stage"],
)

PRICE_COMPARISON_DURATION_SECONDS = Histogram(
    "price_comparison_duration_seconds",
    "Tempo de execução da comparação de preços (segundos)",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0],
)

PRICE_COMPARISON_TASK_LATENCY_SECONDS = Histogram(
    "price_comparison_task_latency_seconds",
    "Tempo total da task Celery de comparação de preços",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10],
)

COMPARISONS_NO_AVAILABLE_COMPETITORS_TOTAL = Counter(
    "comparisons_no_available_competitors_total",
    "Comparações sem concorrentes com preço disponível",
)

__all__ = [
    "PRICE_COMPARISONS_TOTAL",
    "MALFORMED_COMPARISON_PAYLOADS_TOTAL",
    "PRICE_COMPARISON_FAILURES_TOTAL",
    "PRICE_COMPARISON_DURATION_SECONDS",
    "PRICE_COMPARISON_TASK_LATENCY_SECONDS",
    "COMPARISONS_NO_AVAILABLE_COMPETITORS_TOTAL",
]
