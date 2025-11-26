""" Métricas relacionadas ao uso do Redis """

from prometheus_client import Gauge, Counter

REDIS_QUEUE_MESSAGES = Gauge(
    "redis_queue_messages",
    "Total de mensagens pendentes em filas Redis",
    ["queue"],
)

REDIS_MEMORY_USAGE_BYTES = Gauge(
    "redis_memory_usage_bytes",
    "Uso de memória pelo Redis em bytes",
)

REDIS_CONNECTION_ERRORS_TOTAL = Counter(
    "redis_connection_errors_total",
    "Total de falhas ao tentar conectar ao Redis",
)

__all__ = [
    "REDIS_QUEUE_MESSAGES",
    "REDIS_MEMORY_USAGE_BYTES",
    "REDIS_CONNECTION_ERRORS_TOTAL",
]
