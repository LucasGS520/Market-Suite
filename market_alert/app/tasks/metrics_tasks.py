""" Tarefas auxiliares para coleta de métricas de workers """

import time
import structlog
from celery import shared_task, signals
from celery.app.control import Inspect

from utils.redis_client import get_redis_client
from app.core.celery_app import celery_app
from infra.db import get_engine
from app.metrics import (
    CELERY_QUEUE_LENGTH, CELERY_WORKERS_TOTAL,
    CELERY_WORKER_CONCURRENCY, CELERY_TASK_DURATION_SECONDS,
    REDIS_QUEUE_MESSAGES, REDIS_MEMORY_USAGE_BYTES,
    DB_POOL_SIZE, DB_POOL_CHECKOUTS
)
from app.services.services_cache_scraper import cache_manager


logger = structlog.get_logger("metrics_tasks")
redis_client = get_redis_client()

@shared_task(name="app.tasks.metrics_tasks.collect_celery_metrics")
def collect_celery_metrics():
    """ Task periódica que inspeciona filas e workers do celery (Redis) """
    try:
        #Coleta de tarefas pendentes
        queues = ["celery", "scraping", "monitor"]

        #Pendentes já reservados pelos workers (insp.reserved) e agendados (insp.scheduled)
        insp: Inspect = celery_app.control.inspect()
        reserved = insp.reserved() or {}
        scheduled = insp.scheduled() or {}

        pending_reserved = sum(len(tasks) for tasks in reserved.values())
        pending_scheduled = sum(len(tasks) for tasks in scheduled.values())

        #Coleta uso de memória do Redis
        info = redis_client.info(section="memory") or {}
        REDIS_MEMORY_USAGE_BYTES.set(int(info.get("used_memory", 0)))

        #Coleta de Workers e concorrência
        stats = insp.stats() or {}
        total_workers = len(stats)
        CELERY_WORKERS_TOTAL.set(total_workers)

        total_concurrency = sum(
            info.get("pool", {}).get("max-concurrency", 0)
            for info in stats.values()
        )
        CELERY_WORKER_CONCURRENCY.set(total_concurrency)

        for queue_name in queues:
            pending_redis = redis_client.llen(queue_name)
            if queue_name == "celery":
                total_pending = max(pending_redis, pending_reserved + pending_scheduled)
            else:
                total_pending = pending_redis

            CELERY_QUEUE_LENGTH.labels(queue=queue_name).set(total_pending)
            REDIS_QUEUE_MESSAGES.labels(queue=queue_name).set(pending_redis)

            logger.info("collected_celery_metrics", queue=queue_name, pending_redis=pending_redis, pending_reserved=pending_reserved, pending_scheduled=pending_scheduled,
                        total_pending=total_pending, workers=total_workers, concurrency=total_concurrency)

    except Exception as exc:
        logger.error("failed_collecting_celery_metrics", error=str(exc))

#Sinais para medir duração de cada task
@signals.task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **extra):
    """ Armazena timestamp de inicio no objeto da task """
    task.__dict__["_start_time"] = time.time()

@signals.task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **extra):
    """ Calcula duração usando timestamp salvo e envia valor ao histograma """
    start = task.__dict__.get("_start_time")
    if start:
        duration = time.time() - start
        #Registra no histograma
        CELERY_TASK_DURATION_SECONDS.labels(task_name=task.name).observe(duration)

@shared_task(name="app.tasks.metrics_tasks.collect_audit_metrics")
def collect_audit_metrics():
    """ Task periódica de auditoria """
    logger.info("collect_audit_metrics_noop")

@shared_task(name="app.tasks.metrics_tasks.collect_db_metrics")
def collect_db_metrics():
    """ Coleta periódica de métricas do pool de banco """
    try:
        engine = get_engine()
        DB_POOL_SIZE.set(engine.pool.size())
        DB_POOL_CHECKOUTS.set(engine.pool.checkedout())
    except Exception as exc:
        logger.error("failed_collecting_db_metrics", error=str(exc))

@shared_task(name="app.tasks.metrics_tasks.cleanup_cache")
def cleanup_cache() -> int:
    """ Remove entradas antigas do cache de scraping """
    try:
        removed = cache_manager.cleanup()
        logger.info("cache_cleanup", removed=removed)
        return removed
    except Exception as exc:
        logger.error("cache_cleanup_failed", error=str(exc))
        return 0
