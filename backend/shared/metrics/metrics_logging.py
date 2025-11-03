""" Métricas referentes ao volume de logs gerados """

from prometheus_client import Counter

LOG_ENTRIES_TOTAL = Counter(
    "log_entries_total",
    "Total de linhas de log geradas",
    ["level"],
)

__all__ = [
    "LOG_ENTRIES_TOTAL",
]
