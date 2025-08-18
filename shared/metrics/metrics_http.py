""" Métricas de servidor HTTP exposto via FastAPI """

from prometheus_client import Counter, Histogram

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Contador de requisições HTTP recebidas",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUESTS_LATENCY_SECONDS = Histogram(
    "http_request_latency_seconds",
    "Tempo de resposta das requisições HTTP",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

__all__ = [
    "HTTP_REQUESTS_TOTAL",
    "HTTP_REQUESTS_LATENCY_SECONDS",
]
