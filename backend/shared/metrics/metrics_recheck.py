""" Métricas para agendamentos adaptativos de rechecagem """

from prometheus_client import Counter, Histogram

RECHECK_SCHEDULED_TOTAL = Counter(
    "recheck_scheduled_total",
    "Total de rechecagens agendadas",
)

RECHECK_COMPETITORS_ENQUEUED_TOTAL = Counter(
    "recheck_competitors_enqueued_total",
    "Total de concorrentes enfileirados após atualizar um monitorado",
)

RECHECK_ENQUEUE_FAILURES_TOTAL = Counter(
    "recheck_enqueue_failures_total",
    "Falhas ao enfileirar concorrentes vinculados",
)

RECHECK_ENQUEUE_SKIPPED_BY_LIMIT_TOTAL = Counter(
    "recheck_enqueue_skipped_by_limit_total",
    "Concorrentes não enfileirados devido a limites de configuração",
)

ADAPTIVE_INTERVAL_CALCULATED_SECONDS = Histogram(
    "adaptive_interval_calculated_seconds",
    "Intervalo adaptativo calculado para rechecagem (em segundos)",
    buckets=[300, 600, 1200, 1800, 3600, 7200, 14400],
)

ADAPTIVE_INTERVAL_DECISION_TOTAL = Counter(
    "adaptive_interval_decision_total",
    "Decisões de intervalo adaptativo por categoria",
    ["category"],
)

__all__ = [
    "RECHECK_SCHEDULED_TOTAL",
    "RECHECK_COMPETITORS_ENQUEUED_TOTAL",
    "RECHECK_ENQUEUE_FAILURES_TOTAL",
    "RECHECK_ENQUEUE_SKIPPED_BY_LIMIT_TOTAL",
    "ADAPTIVE_INTERVAL_CALCULATED_SECONDS",
    "ADAPTIVE_INTERVAL_DECISION_TOTAL",
]
