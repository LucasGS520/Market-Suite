""" Configura a aplicação Celery do `market_alert` e registra tasks.

Responsabilidade única:
    Configuração pura do Celery (exchanges, filas, serialização, timezone) e
    hooks mínimos de worker que delegam para serviços especializados.

    Lógica operacional extraída para módulos dedicados:
    - Carregamento de tasks  → ``core.task_loader``
    - Autostart/lock do coletor contínuo → ``services.continuous_collector_manager``
"""

import os
import logging
import time

import structlog
from structlog.typing import BindableLogger, EventDict
from celery import Celery
from celery.signals import worker_ready

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
}

logger = structlog.get_logger("celery_app")
PROCESS_START_MONOTONIC = time.monotonic()


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

# ---------------------------------------------------------------------------
# Criação da aplicação Celery
# ---------------------------------------------------------------------------

celery_app = Celery(
    "market_alert",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=TASK_MODULES,
)

# ---------------------------------------------------------------------------
# Carregamento de módulos de tasks
# Garante registro das tasks fora do contexto do worker CLI
# ---------------------------------------------------------------------------

from market_alert.core.task_loader import load_task_modules  # noqa: E402

load_task_modules(TASK_MODULES)

# ---------------------------------------------------------------------------
# Aviso de configuração de TTL do lock de produto
# ---------------------------------------------------------------------------

def _warn_lock_ttl_configuration() -> None:
    """ Avalia se o TTL do lock de produto está abaixo do recomendado """
    configured_ttl = settings.PRODUCT_LOCK_TTL_SECONDS
    min_safe = settings.PRODUCT_LOCK_TTL_MIN_SAFE_SECONDS
    if configured_ttl < min_safe:
        logger.warning(
            "product_lock_ttl_low",
            configured_ttl=configured_ttl,
            min_safe_seconds=min_safe,
        )
    else:
        logger.info(
            "product_lock_ttl_configured",
            configured_ttl=configured_ttl,
            min_safe_seconds=min_safe,
        )

_warn_lock_ttl_configuration()

# ---------------------------------------------------------------------------
# Hook de worker: delega para ContinuousCollectorManager
# ---------------------------------------------------------------------------

@worker_ready.connect
def _start_worker_server(**kwargs):
    """ Inicia rotinas de suporte assim que o worker estiver pronto.

    Delega inteiramente para ``continuous_collector_manager``, mantendo
    este arquivo livre de lógica operacional.
    """
    from market_alert.services.continuous_collector_manager import (
        request_start,
        set_process_start_monotonic,
        start_revalidation_loop,
    )
    set_process_start_monotonic(PROCESS_START_MONOTONIC)
    request_start(celery_app)
    start_revalidation_loop(celery_app)

# ---------------------------------------------------------------------------
# Configurações adicionais do Celery
# Define serialização, fuso horário e limites
# ---------------------------------------------------------------------------

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    worker_hijack_root_logger=False,

    #Concorrência global (podendo ser sobrescrito via CLI)
    worker_concurrency=int(os.getenv("CELERY_WORKER_CONCURRENCY", "12")),

    #Prefetch reduzido mantém processamento sensível com resposta rápida mesmo em alta carga
    worker_prefetch_multiplier=int(os.getenv("CELERY_WORKER_PREFETCH", "1")),
    task_queue_max_priority=10,
)

#Define exchanges e filas dedicadas, separa scraping e monitoramento
celery_app.conf.task_queues = TASK_QUEUES

#Roteamento de tarefas para filas específicas, mantém cada tipo de tarefa em sua fila
