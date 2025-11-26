""" Configura a aplicação Celery do `market_alert` e registra tasks e métricas """

#Registra métricas antes de iniciar o HTTP server
import os
import logging
from importlib import import_module

import structlog
from structlog.typing import BindableLogger, EventDict
from celery import Celery
from celery.signals import task_success, task_failure, worker_ready
from prometheus_client import start_http_server
from shared.metrics.metrics_celery import CELERY_TASKS_TOTAL

try:
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
except Exception:
    CeleryInstrumentor = None

from market_alert.core.config_alert import settings
from market_alert.core.celery_schedule import (
    BEAT_SCHEDULE,
    TASK_MODULES,
    TASK_QUEUES,
    TASK_ROUTES,
)

SERVICE_LABEL = "market_alert_worker"
NOISY_EVENT_NAMES = {
    "channel_vars_missing",
    "collected_celery_metrics",
    "collect_audit_metrics_noop",
}

logger = structlog.get_logger("celery_app")


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
    include=TASK_MODULES,
)

if CeleryInstrumentor:
    #Instrumenta o Celery para observabilidade distribuída
    CeleryInstrumentor().instrument()

def _force_import_task_modules() -> None:
    """ Garante importação explícita dos módulos de tasks registrados 
    
    Celery carrega os módulos listados em ``include`` quando inicializado
    via CLI. Em execuções fora do worker (ex.: testes ou inicialização da
    aplicação) realizamos import explícito para registrar as tasks e evitar
    surpresas com módulos não descobertos.
    """
    for module_path in TASK_MODULES:
        try:
            import_module(module_path)
            logger.debug("task_module_imported", module=module_path)
        except Exception:
            logger.exception("task_module_import_failed", module=module_path)


_force_import_task_modules()

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

#Define exchanges e filas dedicadas, Separa scraping e monitoramento. 
celery_app.conf.task_queues = TASK_QUEUES

#Roteamento de tarefas para filas específicas e mantém cada tipo de tarefa em sua fila
celery_app.conf.task_routes = TASK_ROUTES

#Agendamentos periódicos (Celery Beat), define intervalos de execução de tasks
celery_app.conf.beat_schedule = BEAT_SCHEDULE
