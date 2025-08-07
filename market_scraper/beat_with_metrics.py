""" Executor do Celery Beat com endpoint de métricas Prometheus """

import alert_app.metrics
from prometheus_client import start_http_server
from scraper_app.core.celery_app import celery_app

if __name__ == "__main__":
    #Expõe HTTP server de métricas *Uma unica vez*
    start_http_server(port=8001, addr="0.0.0.0")
    #Inicia o beat
    celery_app.start(argv=["beat", "--loglevel=info"])
