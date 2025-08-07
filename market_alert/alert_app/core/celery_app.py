""" Configuração da aplicação Celery e registro de métricas """

#Registra métricas antes de iniciar o HTTP server
import app.metrics as metrics_module
import os

from kombu import Exchange, Queue
from celery import Celery
from celery.signals import task_success, task_failure, worker_ready
from celery.schedules import crontab
from prometheus_client import start_http_server

try:
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
except Exception:
    CeleryInstrumentor = None

from app.core.config import settings


#Cria a aplicação Celery
celery_app = Celery(
    "market_alert",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "alert_app.tasks.scraper_tasks",
        "alert_app.tasks.monitor_tasks",
        "alert_app.tasks.metrics_tasks",
        "alert_app.tasks.compare_prices_tasks",
        "alert_app.tasks.alert_tasks"
    ]
)

if CeleryInstrumentor:
    #Instrumenta o Celery para observabilidade distribuída
    CeleryInstrumentor().instrument()


@worker_ready.connect
def _start_prometheus_server(**kwargs):
    """ Inicia o servidor Prometheus assim que o worker estiver pronto """
    #Servidor de métricas Prometheus
    start_http_server(port=8002, addr="0.0.0.0")

@task_success.connect
def handle_task_success(sender=None, **kwargs):
    """ Métricas de contagem de sucesso """
    #Incrementa contagem de tasks concluídas
    metrics_module.CELERY_TASKS_TOTAL.labels(task_name=sender.name, status="success").inc()

#Incrementa em toda a falha de task
@task_failure.connect
def handle_task_failure(sender=None, **kwargs):
    """ Métricas de contagem de falha """
    #Incrementa em caso de falha de task
    metrics_module.CELERY_TASKS_TOTAL.labels(task_name=sender.name, status="failure").inc()


#Configurações adicionais do Celery
#Define serialização, fuso horário e limites
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,

    #Limites de tempo de execução
    task_soft_time_limit=30,
    task_time_limit=60,

    #Concorrência global (podendo ser sobrescrito via CLI)
    worker_concurrency=int(os.getenv("CELERY_WORKER_CONCURRENCY", "8")),
)

#Define exchanges e filas dedicadas
#Separa scraping e monitoramento
scraping_exchange = Exchange("scraping", type="direct")
monitor_exchange = Exchange("monitor", type="direct")

celery_app.conf.task_queues = (
    #Fila para tarefas de scraping
    Queue("scraping", scraping_exchange, routing_key="scraping"),
    #Fila para tarefas de monitoramento
    Queue("monitor", monitor_exchange, routing_key="monitor"),
)

#Roteamento de tarefas para filas específicas
#Mantém cada tipo de tarefa em sua fila
celery_app.conf.task_routes = {
    #Todas as scraping tasks vão para fila "scraping"
    "alert_app.tasks.scraper_tasks.collect_product_task": {
        "queue": "scraping", "routing_key": "scraping"
    },
    "alert_app.tasks.scraper_tasks.collect_competitor_task": {
        "queue": "scraping", "routing_key": "scraping"
    },

    #Monitor tasks vão para fila "monitor"
    "alert_app.tasks.monitor_tasks.recheck_monitored_products": {
        "queue": "monitor", "routing_key": "monitor"
    },
    "alert_app.tasks.monitor_tasks.recheck_competitor_products": {
        "queue": "monitor", "routing_key": "monitor"
    }
}

#Agendamentos periódicos (Celery Beat)
#Define intervalos de execução de tasks
celery_app.conf.beat_schedule = {
    #Coleta métricas de celery: a cada 1 minuto
    "collect-celery-metrics-every-1min": {
        "task": "alert_app.tasks.metrics_tasks.collect_celery_metrics",
        "schedule": crontab(minute="*/1"),
        "options": {"queue": "monitor", "routing_key": "monitor"}
    },
    #Coleta métricas de auditoria: a cada 1 minuto
    "collect-audit-metrics-every-1min": {
        "task": "alert_app.tasks.metrics_tasks.collect_audit_metrics",
        "schedule": crontab(minute="*/1"),
        "options": {"queue": "monitor", "routing_key": "monitor"}
    },
    #Coleta métricas de banco: a cada 1 minuto
    "collect-db-metrics-every-1min":{
        "task": "alert_app.tasks.metrics_tasks.collect_db_metrics",
        "schedule": crontab(minute="*/1"),
        "options": {"queue": "monitor", "routing_key": "monitor"}
    },
    #Rechecagem de todos os produtos scraping: a cada 5 minutos
    "recheck-scraping-every-5min": {
        "task": "alert_app.tasks.monitor_tasks.recheck_monitored_products",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "monitor", "routing_key": "monitor"}
    },
    #Rechecagem de todos os produtos concorrentes scraping: a cada 8 minutos
    "recheck-all-competitors-every-8min": {
        "task": "alert_app.tasks.monitor_tasks.recheck_competitor_products",
        "schedule": crontab(minute="*/8"),
        "options": {"queue": "monitor", "routing_key": "monitor"}
    },
    #Limpeza diária do cache de scraping
    "cleanup-cache-daily": {
        "task": "alert_app.tasks.metrics_tasks.cleanup_cache",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "monitor", "routing_key": "monitor"}
    },
}
