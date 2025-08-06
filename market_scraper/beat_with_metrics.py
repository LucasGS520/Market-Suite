""" Executor do Celery Beat com endpoint de métricas Prometheus """

import app.metrics
from prometheus_client import start_http_server
from app.core.celery_app import celery_app

if __name__ == "__main__":
    #Expõe HTTP server de métricas *Uma unica vez*
    start_http_server(port=8001, addr="0.0.0.0")
    #Inicia o beat
    celery_app.start(argv=["beat", "--loglevel=info"])
