""" Worker contínuo para consumo da fila de prioridade de monitorados

Este módulo implementa um loop dedicado que consulta a fila ordenada em Redis,
executa a coleta do monitorado e de seus concorrentes em sequência e recalcula
as janelas de rechecagem com base na estabilidade observada.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session
from billiard.exceptions import TimeLimitExceeded
from celery.exceptions import SoftTimeLimitExceeded

from shared.infra.db import SessionLocal
from shared.metrics.metrics_priority_queue import (
    CONTINUOUS_COLLECTOR_TIME_LIMIT_EXCEEDED_TOTAL,
    CONTINUOUS_COLLECTOR_SOFT_TIMEOUTS_TOTAL,
    PRIORITY_QUEUE_CONSUME_LATENCY_MS,
    PRIORITY_QUEUE_LOOP_ERRORS_TOTAL,
    PRIORITY_QUEUE_PROCESSED_TOTAL,
    PRIORITY_QUEUE_FAILED_BUT_RETAINED_TOTAL,
    PRIORITY_QUEUE_PENDING_REQUEUE_TOTAL,
    PRIORITY_QUEUE_READY_TOTAL,
    PRIORITY_QUEUE_SIZE,
    PRIORITY_QUEUE_STABILITY_TOTAL,
)
from shared.metrics.metrics_scraper import (
    CONTINUOUS_COLLECT_DISPATCH_TOTAL,
    MONITORED_SKIPPED_PAUSED_TOTAL,
)
from shared.utils.redis_client import is_scraping_suspended
from shared.utils.redis_locks import (
    acquire_continuous_collector_lock,
    refresh_continuous_collector_lock,
    release_continuous_collector_lock,
)

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.crud.crud_competitor import get_competitors_by_monitored_id
from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.models.models_products import MonitoredProduct
from market_alert.orchestrator.collector_service_orchestrator import build_monitored_payload, build_competitor_payload
from market_alert.services.services_priority_queue import PriorityQueueService
from market_alert.services.services_priority_queue_manager import enqueue_monitored_at
from market_alert.utils.interval_calculator_products import (
    STABILITY_STABLE,
    STABILITY_UNSTABLE,
    STABILITY_VERY_STABLE,
)


logger = structlog.get_logger("continuous_collector_task")

@dataclass(frozen=True)
class CollectDispatchDecision:
    """ Resultado do disparo assíncrono com orientação de reenfileiramento """
    outcome: str
    next_check_at: datetime | None
    should_requeue: bool
    retain_processing: bool

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

def _update_queue_metrics(
    queue_service: PriorityQueueService,
    *,
    queue_size: int | None = None,
    ready_total: int | None = None,
) -> None:
    """ Atualiza métricas básicas da fila de prioridade """
    resolved_size = queue_size if queue_size is not None else queue_service.size()
    resolved_ready = ready_total if ready_total is not None else queue_service.ready_count()
    PRIORITY_QUEUE_SIZE.set(resolved_size)
    PRIORITY_QUEUE_READY_TOTAL.set(resolved_ready)

def _should_abort(task_request) -> bool:
    """ Verifica se a task foi sinalizada para abortar """
    if task_request is None:
        return False
    abort_fn = getattr(task_request, "is_aborted", None)
    if abort_fn is None:
        return False
    return bool(abort_fn())

def _dispatch_collect_task(
    *,
    payload: dict[str, str | None],
    kind: str,
    monitored_id: str,
    trace_id: str,
    competitor_id: str | None = None,
) -> bool:
    """ Dispara coleta assíncrona mantendo métricas e logs do coletor contínuo """
    try:
        celery_app.send_task(
            "market_alert.tasks.collector_product_task.collect_product_task",
            kwargs={"payload": payload},
            queue="scraping",
        )
        CONTINUOUS_COLLECT_DISPATCH_TOTAL.labels(kind=kind, status="enqueued").inc()
        logger.info(
            "continuous_collect_dispatched",
            kind=kind,
            monitored_id=monitored_id,
            competitor_id=competitor_id,
            trace_id=trace_id,
        )
        return True
    except Exception:
        CONTINUOUS_COLLECT_DISPATCH_TOTAL.labels(kind=kind, status="failed").inc()
        logger.exception(
            "continuous_collect_enqueue_failed",
            kind=kind,
            monitored_id=monitored_id,
            competitor_id=competitor_id,
            trace_id=trace_id,
        )
        return False

def _collect_group(
    *,
    monitored: MonitoredProduct,
    enqueued_at: datetime | None,
) -> CollectDispatchDecision:
    """ Dispara coletas do monitorado e concorrentes retornando decisão de reenqueue """
    with SessionLocal() as db:
        refreshed = get_monitored_product_by_id(db, monitored.id)
        if refreshed:
            #Garante avaliação com status atual antes de iniciar a coleta do grupo
            if refreshed.paused or refreshed.status in {MonitoredStatus.failed}:
                MONITORED_SKIPPED_PAUSED_TOTAL.labels(source="continuous_worker").inc()
                logger.info(
                    "continuous_group_skipped_paused",
                    monitored_id=str(refreshed.id),
                    status=refreshed.status,
                )
                return CollectDispatchDecision(
                    outcome="skipped_paused",
                    next_check_at=None,
                    should_requeue=False,
                    retain_processing=False,
                )
            #Mantém os dados atualizados para o restante do processamento
            db.expunge(refreshed)
            monitored = refreshed

    trace_id = str(uuid4())
    group_started_at = _utc_now()
    group_started_perf = time.perf_counter()

    if monitored.paused or monitored.status in {MonitoredStatus.failed}:
        #Evita coletas em itens pausados para respeitar contrato de pausa
        logger.info(
            "continuous_group_skipped_paused",
            monitored_id=str(monitored.id),
            status=monitored.status,
        )
        return CollectDispatchDecision(
            outcome="skipped_paused",
            next_check_at=None,
            should_requeue=False,
            retain_processing=False,
        )
    
    logger.info(
        "continuous_group_started",
        monitored_id=str(monitored.id),
        collected_at=group_started_at.isoformat(),
        trace_id=trace_id,
    )

    monitored_payload = build_monitored_payload(
        monitored,
        user_id=monitored.user_id,
        enqueued_at=enqueued_at.isoformat() if enqueued_at else None,
    )
    monitored_payload["trace_id"] = trace_id

    _record_enqueue_latency(enqueued_at, group_started_at)

    with SessionLocal() as db:
        competitors = get_competitors_by_monitored_id(
            db,
            monitored.id,
            include_paused=False,
            include_inactive=True, #Inclui itens indisponíveis para rechecagem
        )

    monitored_enqueued = _dispatch_collect_task(
        payload=monitored_payload,
        kind="monitored",
        monitored_id=str(monitored.id),
        trace_id=trace_id,
    )
    if not monitored_enqueued:
        return CollectDispatchDecision(
            outcome="enqueue_failed",
            next_check_at=_utc_now(),
            should_requeue=True,
            retain_processing=False,
        )

    competitor_failures = 0
    for competitor in competitors:
        competitor_payload = build_competitor_payload(
            competitor,
            user_id=monitored.user_id,
            enqueued_at=enqueued_at.isoformat() if enqueued_at else None,
        )
        competitor_payload["trace_id"] = trace_id
        dispatched = _dispatch_collect_task(
            payload=competitor_payload,
            kind="competitor",
            monitored_id=str(monitored.id),
            competitor_id=str(competitor.id),
            trace_id=trace_id,
        )
        if not dispatched:
            competitor_failures += 1

    group_duration_ms = int((time.perf_counter() - group_started_perf) * 1000)
    competitor_total = len(competitors)
    logger.info(
        "continuous_group_dispatched",
        monitored_id=str(monitored.id),
        competitors_total=competitor_total,
        competitors_failed=competitor_failures,
        duration_ms=group_duration_ms,
        trace_id=trace_id,
    )

    if competitor_failures:
        outcome = "enqueued_partial"
    else:
        outcome = "enqueued"
    return CollectDispatchDecision(
        outcome=outcome,
        next_check_at=None,
        should_requeue=False,
        retain_processing=True,
    )

def _requeue_monitored(
    *,
    monitored: MonitoredProduct,
    next_check_at: datetime | None = None,
    queue_service: PriorityQueueService,
) -> bool:
    """ Reenfileira monitorado e informa se houve sucesso no enqueue """
    #Usa a janela calculada pela coleta para garantir o reenqueue correto
    now = _utc_now()
    resolved_next_check_at = next_check_at or monitored.next_check_at or now
    if resolved_next_check_at < now:
        #Evita reenqueue com horário no passado para impedir loops ociosos
        resolved_next_check_at = now
    #Centraliza o reenqueue para registrar métricas e logs padronizados
    if enqueue_monitored_at(
        monitored.id,
        resolved_next_check_at,
        source="continuous_worker",
        queue_service=queue_service,
    ):
        return True
    
    logger.error(
        "continuous_requeue_failed",
        monitored_id=str(monitored.id),
        next_check_at=resolved_next_check_at.isoformat(),
    )
    #Tenta reenfileirar imediatamente para minimizar impacto de falhas transitórias
    if enqueue_monitored_at(
        monitored.id,
        now,
        source="continuous_worker",
        queue_service=queue_service,
    ):
        logger.warning(
            "continuous_requeue_retry_succeeded",
            monitored_id=str(monitored.id),
            next_check_at=now.isoformat(),
        )
        return True

    return False

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
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": None},
    time_limit=None,
    soft_time_limit=None,
)
def run_continuous_collector(self) -> None:
    """ Loop contínuo que consome a fila de prioridade e dispara coletas
    
    Faz polling em intervalo fixo para garantir consumo contínuo sem pausas
    progressivas, mantendo o worker ativo 24/7. Esta task é contínua e não
    deve herdar hard time limit para evitar encerramento forçado do worker.
    """
    bound_logger = logger.bind(task_id=getattr(self.request, "id", None))
    started_at = time.monotonic()
    queue_service = PriorityQueueService()
    batch_size = max(1, int(settings.CONTINUOUS_WORKER_BATCH_SIZE))
    processing_ttl = int(settings.CONTINUOUS_WORKER_PROCESSING_TTL_SECONDS)
    poll_interval = float(settings.CONTINUOUS_WORKER_POLL_INTERVAL)
    lock_ttl_seconds = int(settings.CONTINUOUS_COLLECTOR_LOCK_TTL_SECONDS)
    lock_refresh_interval = max(1.0, lock_ttl_seconds / 2)

    #Garante apenas uma instância ativa do loop contínuo por cluster
    lock_acquired, lock_owner = acquire_continuous_collector_lock(
        ttl_seconds=lock_ttl_seconds,
    )
    if not lock_acquired:
        bound_logger.warning(
            "continuous_collector_lock_denied",
            lock_owner=lock_owner,
        )
        return
    
    last_lock_refresh = time.monotonic()

    try:
        while True:
            processed_ids: list[str] = []
            if _should_abort(getattr(self, "request", None)):
                bound_logger.warning("continuous_worker_aborted")
                return
            
            if time.monotonic() - last_lock_refresh >= lock_refresh_interval:
                if not refresh_continuous_collector_lock(
                    owner_id=lock_owner,
                    ttl_seconds=lock_ttl_seconds,
                ):
                    bound_logger.warning(
                        "continuous_collector_lock_lost",
                        lock_owner=lock_owner,
                    )
                    return
                last_lock_refresh = time.monotonic()
            
            try:
                if is_scraping_suspended():
                    bound_logger.warning("continuous_scraping_suspended")
                    time.sleep(poll_interval)
                    continue
                
                if not queue_service.is_available():
                    bound_logger.error("continuous_queue_unavailable")
                    time.sleep(poll_interval)
                    continue
                
                queue_size = queue_service.size()
                ready_total = queue_service.ready_count()
                _update_queue_metrics(
                    queue_service,
                    queue_size=queue_size,
                    ready_total=ready_total,
                )

                #Mantém um log por ciclo enquanto o lock está válido
                bound_logger.info(
                    "continuous_loop_iteration",
                    queue_size=queue_size,
                    ready_total=ready_total,
                    timestamp=_utc_now().isoformat(),   
                )

                reclaimed = queue_service.reclaim_stale_processing(processing_ttl)
                if reclaimed:
                    #Recoloca itens travados para garantir novas tentativas no loop contínuo
                    bound_logger.warning(
                        "continuous_processing_reclaimed",
                        reclaimed_count=len(reclaimed),
                    )

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
                    try:
                        decision = _collect_group(
                            monitored=monitored,
                            enqueued_at=enqueued_at,
                        )
                    except Exception:
                        decision = CollectDispatchDecision(
                            outcome="error",
                            next_check_at=_utc_now(),
                            should_requeue=True,
                            retain_processing=False,
                        )
                        PRIORITY_QUEUE_LOOP_ERRORS_TOTAL.labels(source="continuous").inc()
                        bound_logger.exception(
                            "continuous_group_failed",
                            monitored_id=str(monitored.id),
                        )
                        
                    PRIORITY_QUEUE_PROCESSED_TOTAL.labels(
                        source="continuous",
                        outcome=decision.outcome,
                    )

                    if decision.retain_processing:
                        #Mantém o item em processamento até a coleta terminar
                        PRIORITY_QUEUE_PENDING_REQUEUE_TOTAL.labels(
                            source="continuous_worker"
                        ).inc()
                    else:
                        processed_ids.append(str(monitored.id))

                    if decision.should_requeue:
                        requeue_success = _requeue_monitored(
                            monitored=monitored,
                            next_check_at=decision.next_check_at,
                            queue_service=queue_service,
                        )
                        if not requeue_success:
                            #Mantém no conjunto de processamento para permitir reclaim futuro
                            PRIORITY_QUEUE_FAILED_BUT_RETAINED_TOTAL.labels(
                                source="continuous_worker"
                            ).inc()
                            bound_logger.warning(
                                "requeue_failed_but_retained",
                                monitored_id=str(monitored.id),
                            )
                            if processed_ids and processed_ids[-1] == str(monitored.id):
                                #Evita erro ao remover IDs quando a lista já foi drenada
                                processed_ids.pop()

                    bound_logger.info(
                        "continuous_item_processed",
                        monitored_id=str(monitored.id),
                        outcome=decision.outcome,
                    )

                if processed_ids:
                    _drain_processing(queue_service, processed_ids)
                    with SessionLocal() as db:
                        _update_stability_metrics(db)
                    _update_queue_metrics(queue_service)
                time.sleep(poll_interval)
            except TimeLimitExceeded:
                #Registra o limite de tempo excedido para sinalizar reinícios forçados
                CONTINUOUS_COLLECTOR_TIME_LIMIT_EXCEEDED_TOTAL.inc()
                bound_logger.warning(
                    "limit_time_collector_exceeded",
                    uptime_seconds=round(time.monotonic() - started_at, 2),
                    reason="time_limit",
                )

                time.sleep(poll_interval)
                continue
            except SoftTimeLimitExceeded:
                #Evita encerrar a task quando o time limit suave ocorre, reiniciando o ciclo
                CONTINUOUS_COLLECTOR_SOFT_TIMEOUTS_TOTAL.inc()
                bound_logger.warning(
                    "continuous_soft_time_limit_exceeded",
                    uptime_seconds=round(time.monotonic() - started_at, 2),
                    reason="soft_time_limit",
                )
                time.sleep(poll_interval)
                continue
            except Exception:
                PRIORITY_QUEUE_LOOP_ERRORS_TOTAL.labels(source="continuous").inc()
                bound_logger.exception("continuous_loop_error")
                time.sleep(poll_interval)

    finally:
        release_continuous_collector_lock(owner_id=lock_owner)
            