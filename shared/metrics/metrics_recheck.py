""" Métricas para agendamentos adaptativos de rechecagem """

from prometheus_client import Counter

RECHECK_SCHEDULED_TOTAL = Counter(
    "recheck_scheduled_total",
    "Total de rechecagens agendadas",
)

__all__ = [
    "RECHECK_SCHEDULED_TOTAL",
]
