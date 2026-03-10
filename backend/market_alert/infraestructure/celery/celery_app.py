""" Instância da aplicação Celery do market_alert.

Responsabilidade única:
    Criar e configurar a instância ``celery_app``. Toda lógica operacional
    foi extraída para módulos dedicados:

    - Configuração de filas/rotas  → ``market_alert.infraestructure.celery.config``
    - Logging do worker            → ``market_alert.infraestructure.logging_config``
    - Hooks de lifecycle           → ``market_alert.infraestructure.worker_lifecycle``
    - Carregamento de tasks        → ``market_alert.infraestructure.task_loader``
    - Políticas de retry           → ``market_alert.infraestructure.celery.retry_policies``
"""

import os
import time

import structlog
from celery import Celery

from market_alert.core.config_alert import settings
from market_alert.infraestructure.celery.config import (
    BEAT_SCHEDULE,
    TASK_MODULES,
    TASK_QUEUES,
    TASK_ROUTES,
)
from market_alert.infraestructure.task_loader import load_task_modules
from market_alert.infraestructure.logging_config import setup_worker_logging
from market_alert.infraestructure.worker_lifecycle import register_worker_signals
from market_alert.infraestructure.startup_validation import validate_startup_dependencies


logger = structlog.get_logger("celery_app")
PROCESS_START_MONOTONIC = time.monotonic()

#Configura logging antes de qualquer uso de logger
setup_worker_logging()

# ---------------------------------------------------------------------------
# Criação da aplicação Celery
# ---------------------------------------------------------------------------

celery_app = Celery(
    "market_alert",
    broker=settings.celery_broker_url,           # db 0 — REDIS_BROKER_DB; sobrescrito por env CELERY_BROKER_URL
    backend=settings.celery_result_backend_url,  # db 1 — REDIS_RESULT_DB; sobrescrito por env CELERY_RESULT_BACKEND
    include=TASK_MODULES,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    worker_hijack_root_logger=False,
    # Concorrência definida exclusivamente no Docker Compose por worker — sem fallback aqui.
    # Decisão 1: scraping=prefork/10, compare=prefork/4, notifications=prefork/4.
    worker_prefetch_multiplier=int(os.getenv("CELERY_WORKER_PREFETCH", "1")),
    task_queue_max_priority=10,
    # TTL explícito: resultados precisam durar apenas até AsyncResult.get() em manager.py
    # COLLECTION_TASK_TIMEOUT=60s; 1h dá margem segura sem acumular memória no Redis.
    result_expires=settings.CELERY_RESULT_EXPIRES,

    # --- Confiabilidade de entrega (Decisão 2) ---
    # Ack só após conclusão da task, não na recepção — garante reentrega se worker morrer.
    task_acks_late=True,
    # Se o processo worker morrer abruptamente (SIGKILL/OOM), recoloca a task na fila.
    # Requer task_acks_late=True para ter efeito.
    task_reject_on_worker_lost=True,

    # --- Time limits globais padrão (Decisão 2) ---
    # Tasks com configuração própria (COLLECTION_RETRY, COMPARISON_RETRY) sobrescrevem estes.
    # Valor padrão para tasks sem time_limit explícito (ex: maintenance_tasks).
    task_soft_time_limit=30,   # lança SoftTimeLimitExceeded → permite cleanup controlado
    task_time_limit=45,        # mata o processo sem clemência após este limite

    # --- Saúde do worker a longo prazo (Decisão 2) ---
    # Recicla processo prefork após N tasks para evitar acúmulo de memory leak.
    worker_max_tasks_per_child=200,

    # --- Visibility timeout do broker Redis (Decisão 2) ---
    # Deve ser > task_time_limit mais longo do sistema (COLLECTION_RETRY.time_limit=120s).
    # Se visibility_timeout < tempo real da task, o broker reentrega enquanto ainda executa.
    broker_transport_options={"visibility_timeout": 3600},  # 1h — cobre qualquer task + margem
)

celery_app.conf.task_queues = TASK_QUEUES
celery_app.conf.task_routes = TASK_ROUTES
celery_app.conf.beat_schedule = BEAT_SCHEDULE

# ---------------------------------------------------------------------------
# Validação de infraestrutura no bootstrap do worker
# ---------------------------------------------------------------------------

#Falha rápida evita subir workers que só irão acumular erro de conexão.
validate_startup_dependencies(strict=True)

# ---------------------------------------------------------------------------
# Registro de signals e carregamento de tasks
# ---------------------------------------------------------------------------

register_worker_signals(celery_app, PROCESS_START_MONOTONIC)

#Carrega tasks explicitamente para garantir registro fora do contexto do worker CLI
load_task_modules(TASK_MODULES)

# ---------------------------------------------------------------------------
# Validação de TTL do lock de produto (aviso operacional no startup)
# ---------------------------------------------------------------------------

_configured_ttl = settings.PRODUCT_LOCK_TTL_SECONDS
_task_time_limit = settings.TASK_GLOBAL_TIME_LIMIT_SECONDS
# Invariante (Decisão 4): lock de produto deve sobreviver ao tempo máximo de execução da task
if _configured_ttl <= _task_time_limit:
    logger.warning(
        "product_lock_ttl_violates_invariant",
        configured_ttl=_configured_ttl,
        task_time_limit=_task_time_limit,
        message="PRODUCT_LOCK_TTL_SECONDS deve ser > TASK_GLOBAL_TIME_LIMIT_SECONDS",
    )
else:
    logger.info(
        "product_lock_ttl_configured",
        configured_ttl=_configured_ttl,
        task_time_limit=_task_time_limit,
        margin_seconds=_configured_ttl - _task_time_limit,
    )
