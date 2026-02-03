""" Métricas referentes ao volume de logs gerados  (no-op stubs)"""

from ._noop_metrics import Counter

LOG_ENTRIES_TOTAL = Counter(
    "log_entries_total",
    "Total de linhas de log geradas",
    ["level"],
)

__all__ = [
    "LOG_ENTRIES_TOTAL",
]
