""" Métricas relacionadas ao uso do Redis  (no-op stubs)"""

from ._noop_metrics import Gauge, Counter

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

REDIS_LOCK_ACQUIRED_TOTAL = Counter(
    "redis_lock_acquired_total",
    "Quantidade de locks adquiridos com sucesso",
    ["resource"],
)

REDIS_LOCK_SKIPPED_TOTAL = Counter(
    "redis_lock_skipped_total",
    "Tentativas de lock ignoradas por já existir",
    ["resource"],
)

REDIS_LOCK_RELEASE_FAILED_TOTAL = Counter(
    "redis_lock_release_failed_total",
    "Falhas ao liberar locks distribuídos no Redis",
    ["resource"],
)

__all__ = [
    "REDIS_QUEUE_MESSAGES",
    "REDIS_MEMORY_USAGE_BYTES",
    "REDIS_CONNECTION_ERRORS_TOTAL",
    "REDIS_LOCK_ACQUIRED_TOTAL",
    "REDIS_LOCK_SKIPPED_TOTAL",
    "REDIS_LOCK_RELEASE_FAILED_TOTAL",
]
