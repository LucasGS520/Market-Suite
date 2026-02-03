""" Métricas específicas de erros da API """

import os

# Importa métricas apropriadas baseado em ENABLE_METRICS
_ENABLE_METRICS = os.getenv("ENABLE_METRICS", "0") in {"1", "true", "True", "yes"}
if _ENABLE_METRICS:
    from prometheus_client import Counter
else:
    from shared.metrics_noop import Counter

API_ERRORS_TOTAL = Counter(
    "api_errors_total",
    "Total de respostas com erro da API",
    ["service", "endpoint", "status_code"],
)

__all__ = ["API_ERRORS_TOTAL"]
