""" Métricas para agendamentos adaptativos de rechecagem  (no-op stubs)"""

from ._noop_metrics import Counter

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

__all__ = [
    "RECHECK_SCHEDULED_TOTAL",
    "RECHECK_COMPETITORS_ENQUEUED_TOTAL",
    "RECHECK_ENQUEUE_FAILURES_TOTAL",
    "RECHECK_ENQUEUE_SKIPPED_BY_LIMIT_TOTAL",
]
