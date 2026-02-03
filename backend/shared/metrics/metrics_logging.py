""" Métricas referentes ao volume de logs gerados """

import os

# Importa métricas apropriadas baseado em ENABLE_METRICS
_ENABLE_METRICS = os.getenv("ENABLE_METRICS", "0") in {"1", "true", "True", "yes"}
if _ENABLE_METRICS:
    from prometheus_client import Counter
else:
    from shared.metrics_noop import Counter

LOG_ENTRIES_TOTAL = Counter(
    "log_entries_total",
    "Total de linhas de log geradas",
    ["level"],
)

__all__ = [
    "LOG_ENTRIES_TOTAL",
]
