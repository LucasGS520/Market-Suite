""" Configura a aplicação Celery do `market_alert` e registra tasks e métricas """

#Registra métricas antes de iniciar o HTTP server
import os
import logging
import threading
import time
from importlib import import_module

import structlog
from structlog.typing import BindableLogger, EventDict
from celery import Celery
from celery.signals import task_success, task_failure, worker_ready
from prometheus_client import start_http_server
from shared.metrics.metrics_celery import CELERY_TASKS_TOTAL, CELERY_CONTINUOUS_AUTOSTART_TOTAL
from shared.utils.redis_client import get_redis_client, set_key_with_ttl

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
CONTINUOUS_COLLECTOR_AUTOSTART_KEY = "market_alert:continuous_collector:autostart"
CONTINUOUS_COLLECTOR_AUTOSTART_COOLDOWN_KEY = "market_alert:continuous_collector:autostart:cooldown"
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

def _continuous_collector_autostart_enabled() -> bool:
    """ Determina se o coletor contínuo deve iniciar automaticamente no worker """
    flag = os.getenv("CONTINUOUS_COLLECTOR_AUTOSTART", "0").strip().lower()
    return flag in {"1", "true", "yes"}

def _continuous_collector_autostart_in_cooldown() -> bool:
    """ Indica se há cooldown ativo para evitar reinícios sucessivos do coletor """
    client = get_redis_client()
    if client is None:
        logger.warning("continuous_autostart_cooldown_check_skipped", reason="redis_unavailable")
        return False
    
    try:
        return bool(client.exists(CONTINUOUS_COLLECTOR_AUTOSTART_COOLDOWN_KEY))
    except Exception:
        logger.exception("continuous_autostart_cooldown_check_failed")
        return False
    
def _register_continuous_collector_cooldown(*, reason: str) -> None:
    """ Registra um cooldown após falha para evitar reinícios em loop """
    cooldown_seconds = int(os.getenv("CONTINUOUS_COLLECTOR_AUTOSTART_COOLDOWN_SECONDS", "120"))
    result = set_key_with_ttl(
        CONTINUOUS_COLLECTOR_AUTOSTART_COOLDOWN_KEY,
        value="1",
        ttl_seconds=cooldown_seconds,
        only_if_absent=True,
    )
    if result is None:
        logger.warning(
            "continuous_autostart_cooldown_unavailable",
            reason="redis_unavailable",
            detail=reason,
        )
        return
    
    logger.info(
        "continuous_autostart_cooldown_registered",
        ttl_seconds=cooldown_seconds,
        detail=reason,
    )

def _delete_continuous_collector_lock() -> None:
    """ Remove o lock do autostart para evitar bloqueios indevidos """
    client = get_redis_client()
    if client is None:
        logger.warning("continuous_autostart_lock_delete_skipped", reason="redis_unavailable")
        return

    try:
        client.delete(CONTINUOUS_COLLECTOR_AUTOSTART_KEY)
    except Exception:
        logger.exception("continuous_autostart_lock_delete_failed")

def _continuous_collector_is_active() -> bool:
    """ Verifica se há execução ativa do coletor contínuo nos workers """
    try:
        inspect = celery_app.control.inspect(timeout=1.0)
        active_tasks = inspect.active() or {}
    except Exception:
        logger.exception("continuous_autostart_inspect_failed")
        return False

    task_name = "market_alert.tasks.continuous_collector_task.run_continuous_collector"
    for tasks in active_tasks.values():
        for task in tasks or []:
            if task.get("name") == task_name:
                return True

    return False

def _request_continuous_collector_start(*, action: str = "triggered") -> None:
    """ Dispara a task contínua apenas uma vez quando habilitada por ambiente """
    if not _continuous_collector_autostart_enabled():
        return
    
    #Evita reinício em loop quando houve falha recente no coletor contínuo
    if _continuous_collector_autostart_in_cooldown():
        logger.warning(
            "continuous_autostart_blocked",
            detail="reinício bloqueado por cooldown",
        )
        return
    
    ttl_seconds = int(os.getenv("CONTINUOUS_COLLECTOR_AUTOSTART_TTL", "60"))
    logger.info(
        "continuous_autostart_requested",
        ttl_seconds=ttl_seconds,
    )
    lock_result = set_key_with_ttl(
        CONTINUOUS_COLLECTOR_AUTOSTART_KEY,
        value="1",
        ttl_seconds=ttl_seconds,
        only_if_absent=True,
    )
    if lock_result is False:
        logger.info("continuous_autostart_skipped", reason="already_running")
        return
    if lock_result is None:
        #Ainda tentamos disparar a task para evitar ficar sem coletas em cenários instáveis
        logger.warning("continuous_autostart_lock_unavailable")

    try:
        celery_app.send_task(
            "market_alert.tasks.continuous_collector_task.run_continuous_collector",
            queue="monitor",
        )
        logger.info("continuous_autostart_triggered", action=action)
        CELERY_CONTINUOUS_AUTOSTART_TOTAL.labels(
            service=SERVICE_LABEL,
            action=action,
        ).inc()
    except Exception:
        _delete_continuous_collector_lock()
        _register_continuous_collector_cooldown(reason="falha ao iniciar coletor contínuo")
        logger.exception("continuous_autostart_failed")

def _revalidate_continuous_collector_lock() -> None:
    """ Revalida periodicamente o lock e reativa o coletor quando necessário """
    if not _continuous_collector_autostart_enabled():
        return
    
    #O lock pode ficar orfão se o worker cair após gravar a chave, mas antes de subir a task
    if _continuous_collector_is_active():
        ttl_seconds = int(os.getenv("CONTINUOUS_COLLECTOR_AUTOSTART_TTL", "60"))
        set_key_with_ttl(
            CONTINUOUS_COLLECTOR_AUTOSTART_KEY,
            value="1",
            ttl_seconds=ttl_seconds,
            only_if_absent=False,
        )
        return
    
    client = get_redis_client()
    if client is None:
        logger.warning("continuous_autostart_recheck_skipped", reason="redis_unavailable")
        return
    
    try:
        has_lock = bool(client.exists(CONTINUOUS_COLLECTOR_AUTOSTART_KEY))
    except Exception:
        logger.exception("continuous_autostart_recheck_failed")
        return
    
    if has_lock:
        #Remove lock orfão antes de tentar reativar a task
        _delete_continuous_collector_lock()

    logger.warning("continuous_autostart_reactivated")
    _request_continuous_collector_start(action="reactivated")

def _start_autostart_revalidation_loop() -> None:
    """ Mantém um loop leve de revalidação para garantir um coletor contínuo ativo """
    if not _continuous_collector_autostart_enabled():
        return
    
    interval_seconds = int(os.getenv("CONTINUOUS_COLLECTOR_AUTOSTART_RECHECK_INTERVAL", "30"))

    def _loop() -> None:
        while True:
            time.sleep(interval_seconds)
            _revalidate_continuous_collector_lock()

    thread = threading.Thread(target=_loop, name="continuous_autostart_revalidation_loop", daemon=True)
    thread.start()

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

@worker_ready.connect
def _start_prometheus_server(**kwargs):
    """ Inicia o servidor Prometheus assim que o worker estiver pronto """
    #Servidor de métricas Prometheus
    start_http_server(port=8002, addr="0.0.0.0")
    _request_continuous_collector_start()
    _start_autostart_revalidation_loop()

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

    #Limites de tempo de execução definidos para task
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
