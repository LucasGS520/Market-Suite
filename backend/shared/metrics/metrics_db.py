""" Métricas de observação do banco de dados """

import os

# Importa métricas apropriadas baseado em ENABLE_METRICS
_ENABLE_METRICS = os.getenv("ENABLE_METRICS", "0") in {"1", "true", "True", "yes"}
if _ENABLE_METRICS:
    from prometheus_client import Gauge
else:
    from shared.metrics_noop import Gauge

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
