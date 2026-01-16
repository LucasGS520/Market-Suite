""" Worker contínuo para consumo da fila de prioridade de monitorados

Este módulo implementa um loop dedicado que consulta a fila ordenada em Redis,
executa a coleta do monitorado e de seus concorrentes em sequência e recalcula
as janelas de rechecagem com base na estabilidade observada.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.infra.db import SessionLocal
from shared.metrics.metrics_priority_queue import (
    PRIORITY_QUEUE_CONSUME_LATENCY_MS,
    PRIORITY_QUEUE_PROCESSED_TOTAL,
    PRIORITY_QUEUE_SIZE,
    PRIORITY_QUEUE_STABILITY_TOTAL,
)
from shared.metrics.metrics_scraper import MONITORED_SKIPPED_PAUSED_TOTAL
from shared.utils.redis_client import is_scraping_suspended

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.crud.crud_competitor import get_competitors_by_monitored_id
from market_alert.crud.crud_monitored import get_monitored_product_by_id, get_last_price_change_for_monitored
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.models.models_products import MonitoredProduct
from market_alert.orchestrator.collector_service_orchestrator import build_monitored_payload, build_competitor_payload, enqueue_collect
from market_alert.services.services_priority_queue import PriorityQueueService
from market_alert.tasks.collector_product_task import collect_product
from market_alert.tasks.recheck_scheduler_task import schedule_rechecks
from market_alert.utils.interval_calculator_products import (
    calculate_next_check_at,
    calculate_stability_score,
    STABILITY_STABLE,
    STABILITY_UNSTABLE,
    STABILITY_VERY_STABLE,
)


logger = structlog.get_logger("continuous_collector_task")

def _utc_now() -> datetime:
    """ Retorna timestamp em UTC sem microssegundos para logs e métricas """
    return datetime.now(timezone.utc).replace(microsecond=0)

def _normalize_enqueued_at(enqueued_at: datetime | None) -> datetime | None:
    """ Normaliza o timestamp de enfileiramento para UTC """
    if enqueued_at is None:
        return None
    if enqueued_at.tzinfo is None:
        return enqueued_at.replace(tzinfo=timezone.utc)
    return enqueued_at.astimezone(timezone.utc)

def _update_stability_metrics(db: Session) -> None:
    """ Atualiza métricas agregadas por faixa de estabilidade """
    stability_column = func.coalesce(MonitoredProduct.stability_score, STABILITY_UNSTABLE)
    counts = (
        db.query(stability_column, func.count(MonitoredProduct.id))
        .group_by(stability_column)
        .all()
    )
    normalized = {score: int(count) for score, count in counts}
    PRIORITY_QUEUE_STABILITY_TOTAL.labels(stability="unstable").set(
        normalized.get(STABILITY_UNSTABLE, 0)
    )
    PRIORITY_QUEUE_STABILITY_TOTAL.labels(stability="stable").set(
        normalized.get(STABILITY_STABLE, 0)
    )
    PRIORITY_QUEUE_STABILITY_TOTAL.labels(stability="very_stable").set(
        normalized.get(STABILITY_VERY_STABLE, 0)
    )

def _record_enqueue_latency(enqueued_at: datetime | None, collected_at: datetime) -> None:
    """ Registra latência entre enfileiramento e início da coleta """
    normalized = _normalize_enqueued_at(enqueued_at)
    if normalized is None:
        return
    latency_ms = max(int((collected_at - normalized).total_seconds() * 1000), 0)
    PRIORITY_QUEUE_CONSUME_LATENCY_MS.observe(latency_ms)

def _collect_group(
    *,
    monitored: MonitoredProduct,
    enqueued_at: datetime | None,
) -> str:
    """ Coleta monitorado e concorrentes em sequência retornando desfecho """
    trace_id = str(uuid4())
    group_started_at = _utc_now()

    monitored_payload = build_monitored_payload(
        monitored,
        user_id=monitored.user_id,
        enqueued_at=enqueued_at.isoformat() if enqueued_at else None,
    )
    monitored_payload["trace_id"] = trace_id

    _record_enqueue_latency(enqueued_at, group_started_at)
    outcome, monitored_result = collect_product(
        monitored_payload,
        use_lock=True,
        dispatch_comparison=True,
        logger_bound=logger.bind(monitored_id=str(monitored.id), trace_id=trace_id),
    )

    with SessionLocal() as db:
        competitors = get_competitors_by_monitored_id(
            db,
            monitored.id,
            include_paused=False,
            include_inactive=False,
        )
        for competitor in competitors:
            competitor_payload = build_competitor_payload(
                competitor,
                user_id=monitored.user_id,
                enqueued_at=enqueued_at.isoformat() if enqueued_at else None,
            )
            competitor_payload["trace_id"] = trace_id
            collect_product(
                competitor_payload,
                use_lock=True,
                dispatch_comparison=True,
                logger_bound=logger.bind(
                    monitored_id=str(monitored.id),
                    competitor_id=str(competitor.id),
                    trace_id=trace_id,
                ),
            )

    group_finished_at = _utc_now()
    with SessionLocal() as db:
        refreshed = get_monitored_product_by_id(db, monitored.id)
        if refreshed:
            refreshed.group_collected_at = group_finished_at
            refreshed.last_price_change_at = get_last_price_change_for_monitored(
                db,
                refreshed.id,
            )
            refreshed.stability_score = calculate_stability_score(
                refreshed,
                reference_time=group_finished_at,
            )
            refreshed.next_check_at = calculate_next_check_at(
                refreshed,
                collected_at=group_finished_at,
            )
            db.commit()

    if monitored_result and monitored_result.status:
        PRIORITY_QUEUE_PROCESSED_TOTAL.labels(outcome=monitored_result.status).inc()
    else:
        PRIORITY_QUEUE_PROCESSED_TOTAL.labels(outcome=outcome).inc()

    return outcome

def _requeue_monitored(
    *,
    monitored: MonitoredProduct,
    queue_service: PriorityQueueService,
    fallback_payload: dict[str, str],
) -> None:
    """ Reenfileira monitorado ou utiliza fallback via Celery """
    next_check_at = monitored.next_check_at or _utc_now()
    enqueued = queue_service.enqueue(str(monitored.id), next_check_at)
    if enqueued:
        queue_service.set_enqueued_at(str(monitored.id), _utc_now())
        return
    
    #Fallback via Celery quando Redis falhar
    delay_seconds = max(int((next_check_at - _utc_now()).total_seconds()), 0)
    enqueue_collect(fallback_payload, countdown=delay_seconds)

def _load_monitored(db: Session, monitored_id: str) -> MonitoredProduct | None:
    """ Carrega monitorado por ID garantindo UUID válido """
    try:
        parsed_id = UUID(monitored_id)
    except Exception:
        return None
    return get_monitored_product_by_id(db, parsed_id)

def _drain_processing(queue_service: PriorityQueueService, product_ids: Iterable[str]) -> None:
    """ Remove itens processados do conjunto auxiliar de processamento """
    queue_service.drain_processing(product_ids)


@celery_app.task(
    bind=True,
    name="market_alert.tasks.continuous_collector_task.run_continuous_collector",
    queue="monitor",
    acks_late=True,
)
def run_continuous_collector(self) -> None:
    """ Loop contínuo que consome a fila de prioridade e dispara coletas """
    bound_logger = logger.bind(task_id=getattr(self.request, "id", None))
    queue_service = PriorityQueueService()
    batch_size = max(1, int(settings.CONTINUOUS_WORKER_BATCH_SIZE))

    while True:
        if is_scraping_suspended():
            bound_logger.warning("continuous_scraping_suspended")
            time.sleep(settings.CONTINUOUS_WORKER_IDLE_SLEEP)
            continue
        
        if not queue_service.is_available():
            #Fallback para o comportamento anterior quando Redis estiver indisponível
            bound_logger.warning("continuous_queue_unavailable_fallback")
            with SessionLocal() as db:
                schedule_rechecks(db, logger_bound=bound_logger)
            time.sleep(settings.CONTINUOUS_WORKER_IDLE_SLEEP)
            continue
        
        processed_ids: list[str] = []
        for _ in range(batch_size):
            next_id = queue_service.pop_due()
            if not next_id:
                break
            
            with SessionLocal() as db:
                monitored = _load_monitored(db, next_id)
                if monitored is None:
                    bound_logger.warning("continuous_monitored_missing", monitored_id=next_id)
                    processed_ids.append(next_id)
                    continue
                
                if monitored.paused or monitored.status in {MonitoredStatus.failed}:
                    MONITORED_SKIPPED_PAUSED_TOTAL.labels(source="continuous_worker").inc()
                    bound_logger.info(
                        "continuous_skipped_paused",
                        monitored_id=str(monitored.id),
                    )
                    processed_ids.append(str(monitored.id))
                    continue
                
            enqueued_at = queue_service.get_enqueued_at(next_id)
            outcome = _collect_group(
                monitored=monitored,
                enqueued_at=enqueued_at,
            )

            processed_ids.append(str(monitored.id))

            with SessionLocal() as db:
                refreshed = get_monitored_product_by_id(db, monitored.id)
                if refreshed is None:
                    continue
                fallback_payload = build_monitored_payload(
                    refreshed,
                    user_id=refreshed.user_id,
                )
                fallback_payload["trace_id"] = str(UUID(int=0))
                _requeue_monitored(
                    monitored=refreshed,
                    queue_service=queue_service,
                    fallback_payload=fallback_payload,
                )

            bound_logger.info(
                "continuous_item_processed",
                monitored_id=str(monitored.id),
                outcome=outcome,
            )

        if processed_ids:
            _drain_processing(queue_service, processed_ids)
            with SessionLocal() as db:
                _update_stability_metrics(db)
            PRIORITY_QUEUE_SIZE.set(queue_service.size())
            time.sleep(settings.CONTINUOUS_WORKER_POLL_INTERVAL)
        else:
            PRIORITY_QUEUE_SIZE.set(queue_service.size())
            time.sleep(settings.CONTINUOUS_WORKER_IDLE_SLEEP)
            