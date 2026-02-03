""" Métricas no-op para API (stubs) """

from ._noop_metrics import Counter

API_ERRORS_TOTAL = Counter(
    "api_errors_total",
    "Total de respostas com erro da API",
    ["service", "endpoint", "status_code"],
)

__all__ = ["API_ERRORS_TOTAL"]
