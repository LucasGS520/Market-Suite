""" Configura a aplicação Celery do `market_alert` com métricas padronizadas """

#Registra métricas antes de iniciar o HTTP server
import os
import logging

import structlog
from structlog.typing import BindableLogger, EventDict
from kombu import Exchange, Queue
from celery import Celery
from celery.signals import task_success, task_failure, worker_ready
from celery.schedules import crontab
from prometheus_client import start_http_server
from shared.metrics.metrics_celery import CELERY_TASKS_TOTAL

try:
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
except Exception:
    CeleryInstrumentor = None

from market_alert.core.config_alert import settings


SERVICE_LABEL = "market_alert_worker"
NOISY_EVENT_NAMES = {
    "channel_vars_missing",
    "collected_celery_metrics",
    "collect_audit_metrics_noop",
}

def drop_repeated_events(
    _logger: BindableLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """ Remove eventos conhecidos que apenas repetem ruído operacional """
    #Ignora mensagens de debug conhecidos que poluem continuamente os logs do worker
    if event_dict.get("event") in NOISY_EVENT_NAMES:
        raise structlog.DropEvent
    
    return event_dict

def configure_worker_logging() -> None:
    """ Configura logs estruturados e silencia bibliotecas barulhentas no worker """
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            drop_repeated_events,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=[structlog.processors.TimeStamper(fmt="iso")]
    ))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    noisy_loggers = (
        "httpx",
        "httpcore",
        "anyio",
        "uvicorn",
        "asyncio",
        "celery",
        "celery.worker.pidbox",
        "celery.worker.pool",
        "celery.worker.consumer",
        "celery.worker.strategy",
        "celery.app.trace",
        "kombu",
    )

    #Mantém logs de erro, mas oculta detalhes de debug que não ajudam na operação diária
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


configure_worker_logging()

#Cria a aplicação Celery
celery_app = Celery(
    "market_alert",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "market_alert.tasks.scraper_tasks",
        "market_alert.tasks.monitor_tasks",
        "market_alert.tasks.metrics_tasks",
        "market_alert.tasks.compare_prices_tasks",
        "market_alert.tasks.alert_tasks"
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
    CELERY_TASKS_TOTAL.labels(
        service=SERVICE_LABEL,
        task_name=sender.name,
        status="success",
    ).inc()

#Incrementa em toda a falha de task
@task_failure.connect
def handle_task_failure(sender=None, **kwargs):
    """ Métricas de contagem de falha """
    #Incrementa em caso de falha de task
    CELERY_TASKS_TOTAL.labels(
        service=SERVICE_LABEL,
        task_name=sender.name,
        status="failure",
    ).inc()


#Configurações adicionais do Celery
#Define serialização, fuso horário e limites
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    worker_hijack_root_logger=False,

    #Limites de tempo de execução
    task_soft_time_limit=30,
    task_time_limit=60,

    #Concorrência global (podendo ser sobrescrito via CLI)
    worker_concurrency=int(os.getenv("CELERY_WORKER_CONCURRENCY", "12")),

    #Prefetch reduzido mantém processamento sensível com resposta rápida mesmo em alta carga
    worker_prefetch_multiplier=int(os.getenv("CELERY_WORKER_PREFETCH", "1")),
    task_queue_max_priority=10,
)

#Define exchanges e filas dedicadas
#Separa scraping e monitoramento. 
#Comparações utilizam a fila padrão para simplificar roteamento e evitar prioridades customizadas.
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
    "market_alert.tasks.scraper_tasks.collect_product_task": {
        "queue": "scraping", "routing_key": "scraping"
    },
    "market_alert.tasks.scraper_tasks.collect_competitor_task": {
        "queue": "scraping", "routing_key": "scraping"
    },

    #Monitor tasks vão para fila "monitor"
    "market_alert.tasks.monitor_tasks.recheck_monitored_products": {
        "queue": "monitor", "routing_key": "monitor"
    },
    "market_alert.tasks.monitor_tasks.recheck_competitor_products": {
        "queue": "monitor", "routing_key": "monitor"
    },
}

#Agendamentos periódicos (Celery Beat)
#Define intervalos de execução de tasks
celery_app.conf.beat_schedule = {
    #Coleta métricas de celery: a cada 1 minuto
    "collect-celery-metrics-every-1min": {
        "task": "market_alert.tasks.metrics_tasks.collect_celery_metrics",
        "schedule": crontab(minute="*/1"),
        "options": {"queue": "monitor", "routing_key": "monitor"}
    },
    #Coleta métricas de auditoria: a cada 1 minuto
    "collect-audit-metrics-every-1min": {
        "task": "market_alert.tasks.metrics_tasks.collect_audit_metrics",
        "schedule": crontab(minute="*/1"),
        "options": {"queue": "monitor", "routing_key": "monitor"}
    },
    #Coleta métricas de banco: a cada 1 minuto
    "collect-db-metrics-every-1min":{
        "task": "market_alert.tasks.metrics_tasks.collect_db_metrics",
        "schedule": crontab(minute="*/1"),
        "options": {"queue": "monitor", "routing_key": "monitor"}
    },
    #Rechecagem de todos os produtos scraping: a cada 5 minutos
    "recheck-scraping-every-5min": {
        "task": "market_alert.tasks.monitor_tasks.recheck_monitored_products",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "monitor", "routing_key": "monitor"}
    },
    #Rechecagem de todos os produtos concorrentes scraping: a cada 8 minutos
    "recheck-all-competitors-every-8min": {
        "task": "market_alert.tasks.monitor_tasks.recheck_competitor_products",
        "schedule": crontab(minute="*/8"),
        "options": {"queue": "monitor", "routing_key": "monitor"}
    },
    #Limpeza diária do cache de scraping
    "cleanup-cache-daily": {
        "task": "market_alert.tasks.metrics_tasks.cleanup_cache",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "monitor", "routing_key": "monitor"}
    },
}
