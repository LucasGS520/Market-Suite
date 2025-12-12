""" Agendador simplificado de rechecagens periódicas.

Este módulo substitui o fluxo complexo de `monitor_recheck_tasks.py` por uma
abordagem direta: apenas enfileira tasks `collect_product_task` para produtos
com `next_check_at` vencido. O controle de concorrência é feito via locks Redis
(já implementado e funcional em `collect_product_task`), eliminando a
necessidade de flags no banco de dados.
"""
from datetime import datetime, timezone
import random

import structlog
from celery.exceptions import SoftTimeLimitExceeded

from shared.infra.db import SessionLocal
from shared.metrics.metrics_scraper import (
    RECHECK_DISPATCH_TOTAL,
    RECHECK_ENQUEUED_TOTAL,
    RECHECK_NEXT_CHECK_MISSING_TOTAL,
    RECHECK_SKIPPED_NO_NEXT_CHECK_TOTAL,
    SCRAPING_LATENCY_SECONDS,
)
from shared.utils.redis_client import is_scraping_suspended

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.enums.enums_products import MonitoringType, MonitoredStatus
from market_alert.models.models_products import MonitoredProduct


logger = structlog.get_logger("recheck_scheduler")


@celery_app.task(
    bind=True,
    max_retries=0,
    name="market_alert.tasks.recheck_scheduler_task.schedule_rechecks",
    queue="monitor",
)
def schedule_rechecks(self) -> int:
    """ Enfileira coletas de produtos com janela de rechecagem vencida.
    
    A task varre produtos com `next_check_at <= now` e agenda
    `collect_product_task` na fila `scraping`. O comportamento é idêntico ao
    onboarding inicial: cada produto é coletado independentemente, aplicando
    lock Redis para evitar duplicidades.
    
    Returns:
        int: Quantidade de produtos enfileirados.
    """
    from market_alert.tasks.collector_product_task import collect_product_task
    from market_alert.orchestrator.collector_service_orchestrator import (
        build_monitored_payload,
    )
    
    started_at = datetime.now(timezone.utc)
    task_logger = logger.bind(
        task_id=getattr(self.request, "id", None),
        phase="scheduler",
    )
    
    try:
        if is_scraping_suspended():
            task_logger.warning("scheduler_skipped_suspended")
            return 0
        
        reference = started_at.replace(microsecond=0)
        dispatched = 0
        
        with SessionLocal() as db:
            #Contabiliza produtos sem next_check_at para métricas
            missing_next = (
                db.query(MonitoredProduct)
                .filter(
                    MonitoredProduct.monitoring_type == MonitoringType.scraping,
                    MonitoredProduct.next_check_at.is_(None),
                )
                .count()
            )
            if missing_next:
                RECHECK_SKIPPED_NO_NEXT_CHECK_TOTAL.labels(
                    reason="missing_next_check_at"
                ).inc(missing_next)
                RECHECK_NEXT_CHECK_MISSING_TOTAL.inc(missing_next)
                task_logger.info(
                    "recheck_skip_missing_next_check_at",
                    count=missing_next,
                    batch_limit=settings.RECHECK_ENQUEUE_BATCH_SIZE,
                )
            
            #Seleciona candidatos elegíveis para rechecagem
            due_candidates = (
                db.query(MonitoredProduct)
                .filter(
                    MonitoredProduct.monitoring_type == MonitoringType.scraping,
                    MonitoredProduct.status != MonitoredStatus.failed,
                    MonitoredProduct.next_check_at.isnot(None),
                    MonitoredProduct.next_check_at <= reference,
                )
                .order_by(MonitoredProduct.next_check_at)
                .limit(settings.RECHECK_ENQUEUE_BATCH_SIZE)
                .all()
            )
            
            if len(due_candidates) == settings.RECHECK_ENQUEUE_BATCH_SIZE:
                task_logger.info(
                    "recheck_batch_limit_reached",
                    limit=settings.RECHECK_ENQUEUE_BATCH_SIZE,
                    reference_time=reference.isoformat(),
                )
            
            #Enfileira cada produto na fila de scraping
            for monitored in due_candidates:
                jitter = random.uniform(0, settings.RECHECK_ENQUEUE_JITTER_SECONDS)
                payload = build_monitored_payload(
                    monitored,
                    user_id=monitored.user_id,
                )
                
                collect_product_task.apply_async(
                    kwargs={"payload": payload},
                    queue="scraping",
                    countdown=jitter,
                )
                
                RECHECK_DISPATCH_TOTAL.labels(status="dispatched").inc()
                RECHECK_ENQUEUED_TOTAL.labels(status="due").inc()
                dispatched += 1
        
        task_logger.info("scheduler_dispatched", dispatched=dispatched)
        return dispatched
    
    except SoftTimeLimitExceeded:
        task_logger.warning("scheduler_timeout")
        return 0
    
    except Exception:
        task_logger.exception("scheduler_failed")
        raise
    
    finally:
        duration = (datetime.now(timezone.utc) - started_at).total_seconds()
        SCRAPING_LATENCY_SECONDS.labels(source="recheck_scheduler").observe(duration)


__all__ = ["schedule_rechecks"]
