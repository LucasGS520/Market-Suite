""" Instância da aplicação Celery do market_alert.

Responsabilidade única:
    Criar e configurar a instância ``celery_app``. Toda lógica operacional
    foi extraída para módulos dedicados:

    - Configuração de filas/rotas  → ``infra.celery.config``
    - Logging do worker            → ``core.logging_config``
    - Hooks de lifecycle           → ``infra.worker_lifecycle``
    - Carregamento de tasks        → ``core.task_loader``
    - Políticas de retry           → ``infra.celery.retry_policies``
"""

import os
import time

import structlog
from celery import Celery

from market_alert.core.config_alert import settings
from market_alert.core.logging_config import setup_worker_logging
from market_alert.core.task_loader import load_task_modules
from market_alert.infra.celery.config import (
    BEAT_SCHEDULE,
    TASK_MODULES,
    TASK_QUEUES,
    TASK_ROUTES,
)
from market_alert.infra.worker_lifecycle import register_worker_signals
from market_alert.infra.startup_validation import validate_startup_dependencies


logger = structlog.get_logger("celery_app")
PROCESS_START_MONOTONIC = time.monotonic()

#Configura logging antes de qualquer uso de logger
setup_worker_logging()

# ---------------------------------------------------------------------------
# Criação da aplicação Celery
# ---------------------------------------------------------------------------

celery_app = Celery(
    "market_alert",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=TASK_MODULES,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    worker_hijack_root_logger=False,
    worker_concurrency=int(os.getenv("CELERY_WORKER_CONCURRENCY", "12")),
    worker_prefetch_multiplier=int(os.getenv("CELERY_WORKER_PREFETCH", "1")),
    task_queue_max_priority=10,
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
_min_safe = settings.PRODUCT_LOCK_TTL_MIN_SAFE_SECONDS
if _configured_ttl < _min_safe:
    logger.warning(
        "product_lock_ttl_low",
        configured_ttl=_configured_ttl,
        min_safe_seconds=_min_safe,
    )
else:
    logger.info(
        "product_lock_ttl_configured",
        configured_ttl=_configured_ttl,
        min_safe_seconds=_min_safe,
    )
