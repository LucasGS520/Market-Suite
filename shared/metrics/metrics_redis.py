""" Métricas relacionadas ao uso do Redis """

from prometheus_client import Gauge

REDIS_QUEUE_MESSAGES = Gauge(
    "redis_queue_messages",
    "Total de mensagens pendentes em filas Redis",
    ["queue"],
)

REDIS_MEMORY_USAGE_BYTES = Gauge(
    "redis_memory_usage_bytes",
    "Uso de memória pelo Redis em bytes",
)

__all__ = [
    "REDIS_QUEUE_MESSAGES",
    "REDIS_MEMORY_USAGE_BYTES",
]
