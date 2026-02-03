"""Executor do Celery Beat com endpoint de métricas Prometheus."""

import os
from shared import metrics

# Importa prometheus_client condicionalmente
_ENABLE_METRICS = os.getenv("ENABLE_METRICS", "0") in {"1", "true", "True", "yes"}
if _ENABLE_METRICS:
    from prometheus_client import start_http_server
else:
    from shared.metrics_noop import start_http_server

from market_alert.core.celery_app import celery_app

if __name__ == "__main__":
    #Expõe HTTP server de métricas UMA UNICA VEZ (apenas se habilitado)
    if _ENABLE_METRICS:
        start_http_server(port=8001, addr="0.0.0.0")
    #Inicia o beat
    celery_app.start(argv=["beat", "--loglevel=info"])
