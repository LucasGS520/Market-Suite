""" Métricas de observação do banco de dados  (no-op stubs)"""

from ._noop_metrics import Gauge

DB_POOL_SIZE = Gauge(
    "db_pool_size",
    "Tamanho do pool de conexões do banco de dados",
)

DB_POOL_CHECKOUTS = Gauge(
    "db_pool_checkouts",
    "Número de conexões ativas no pool de banco de dados",
)

__all__ = [
    "DB_POOL_SIZE",
    "DB_POOL_CHECKOUTS",
]
