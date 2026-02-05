""" Worker contínuo para consumo da fila de prioridade de monitorados

Este módulo implementa um loop dedicado que consulta a fila ordenada em Redis,
executa a coleta do monitorado e de seus concorrentes em sequência e recalcula
as janelas de rechecagem com base na estabilidade observada.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy.orm import Session
from billiard.exceptions import TimeLimitExceeded
from celery.exceptions import SoftTimeLimitExceeded
from celery.canvas import Signature

from shared.infra.db import SessionLocal
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
    """ Retorna timestamp em UTC sem microssegundos para logs """
    return datetime.now(timezone.utc).replace(microsecond=0)

def _resolve_next_check_at(
    monitored: MonitoredProduct,
    next_check_at: datetime | None,
) -> tuple[datetime, datetime]:
    """ Resolve o próximo check garantindo data válida e retorna também o horário base """
    now = _utc_now()
    resolved_next_check_at = next_check_at or monitored.next_check_at or now
    if resolved_next_check_at < now:
        #Evita reenqueue com horário no passado para impedir loops ociosos
        resolved_next_check_at = now
    return resolved_next_check_at, now

def _parse_next_retry_at(value: str | None) -> datetime | None:
    """ Converte string ISO de retry para datetime com timezone """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def _parse_collect_result(collect_result: Any) -> dict[str, Any]:
    """ Normaliza o retorno da task de coleta preservando compatibilidade """
    if isinstance(collect_result, Mapping):
        return dict(collect_result)
    if isinstance(collect_result, str):
        return {"outcome": collect_result, "status": collect_result, "reason": collect_result}
    return {"outcome": "unknown", "status": "unknown", "reason": "unknown"}

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
    on_complete: Signature | None = None,
    on_error: Signature | None = None,
) -> bool:
    """ Dispara coleta assíncrona mantendo logs do coletor contínuo """
    try:
        celery_app.send_task(
            "market_alert.tasks.collector_product_task.collect_product_task",
            kwargs={"payload": payload},
            queue="scraping",
            link=on_complete,
            link_error=on_error,
        )
        logger.info(
            "continuous_collect_dispatched",
            kind=kind,
            monitored_id=monitored_id,
            competitor_id=competitor_id,
            trace_id=trace_id,
        )
        return True
    except Exception:
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
        on_complete=celery_app.signature(
            "market_alert.tasks.continuous_collector_task.finalize_processing_requeue",
            args=[str(monitored.id)],
            kwargs={"trace_id": trace_id},
        ).set(queue="monitor"),
        on_error=celery_app.signature(
            "market_alert.tasks.continuous_collector_task.finalize_processing_requeue_error",
            args=[str(monitored.id)],
            kwargs={"trace_id": trace_id},
        ).set(queue="monitor"),
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
) -> tuple[bool, datetime]:
    """ Reenfileira monitorado e informa se houve sucesso no enqueue """
    #Usa a janela calculada pela coleta para garantir o reenqueue correto
    resolved_next_check_at, now = _resolve_next_check_at(monitored, next_check_at)
    #Centraliza o reenqueue para registrar logs padronizados
    if enqueue_monitored_at(
        monitored.id,
        resolved_next_check_at,
        source="continuous_worker",
        queue_service=queue_service,
    ):
        return True, resolved_next_check_at
    
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
        return True, now

    return False, resolved_next_check_at

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

def _handle_processing_requeue(
    *,
    monitored_id: str,
    collect_outcome: str | None,
    reason: str,
    trace_id: str | None = None,
    next_retry_at: datetime | None = None,
) -> None:
    """ Conclui o fluxo de processamento movendo o item de volta para o ready """
    queue_service = PriorityQueueService()
    normalized_reason = reason or collect_outcome or "unknown"

    with SessionLocal() as db:
        monitored = _load_monitored(db, monitored_id)
        if monitored is None:
            logger.warning(
                "continuous_processing_missing",
                monitored_id=monitored_id,
                reason="monitored_missing",
                trace_id=trace_id,
            )
            queue_service.drain_processing([monitored_id])
            return
        
        resolved_next_check_at, _ = _resolve_next_check_at(monitored, next_retry_at)
        requeued, effective_next_check_at = _requeue_monitored(
            monitored=monitored,
            next_check_at=resolved_next_check_at,
            queue_service=queue_service,
        )

    if requeued:
        queue_service.drain_processing([monitored_id])
        logger.info(
            "continuous_processing_returned_to_ready",
            monitored_id=monitored_id,
            next_check_at=effective_next_check_at.isoformat(),
            reason=normalized_reason,
            outcome=collect_outcome,
            trace_id=trace_id,
        )
        return
    
    logger.warning(
        "continuous_processing_requeue_failed",
        monitored_id=monitored_id,
        next_check_at=effective_next_check_at.isoformat(),
        reason=normalized_reason,
        outcome=collect_outcome,
        trace_id=trace_id,
    )

@celery_app.task(
    name="market_alert.tasks.continuous_collector_task.finalize_processing_requeue",
    queue="monitor",
)
def finalize_processing_requeue(
    collect_result: Any,
    monitored_id: str,
    trace_id: str | None = None,
) -> None:
    """ Reenfileira monitorado após a coleta finalizar e remove do processamento """
    normalized = _parse_collect_result(collect_result)
    next_retry_at = _parse_next_retry_at(normalized.get("next_retry_at"))
    _handle_processing_requeue(
        monitored_id=monitored_id,
        collect_outcome=normalized.get("outcome"),
        reason=normalized.get("status") or normalized.get("reason") or normalized.get("outcome") or "unknown",
        trace_id=trace_id,
        next_retry_at=next_retry_at,
    )

@celery_app.task(
    name="market_alert.tasks.continuous_collector_task.finalize_processing_requeue_error",
    queue="monitor",
)
def finalize_processing_requeue_error(
    request,
    exc,
    traceback,
    monitored_id: str,
    trace_id: str | None = None,
) -> None:
    """ Reenfileira monitorado quando a task de coleta falha inesperadamente """
    _handle_processing_requeue(
        monitored_id=monitored_id,
        collect_outcome=None,
        reason="collect_task_exception",
        trace_id=trace_id,
    )

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
                        bound_logger.exception(
                            "continuous_group_failed",
                            monitored_id=str(monitored.id),
                        )

                    if decision.retain_processing:
                        #Mantém o item em processamento até a coleta terminar
                        pass
                    
                    else:
                        processed_ids.append(str(monitored.id))

                    if decision.should_requeue:
                        requeue_success, _ = _requeue_monitored(
                            monitored=monitored,
                            next_check_at=decision.next_check_at,
                            queue_service=queue_service,
                        )
                        if not requeue_success:
                            #Mantém no conjunto de processamento para permitir reclaim futuro
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
                time.sleep(poll_interval)
            except TimeLimitExceeded:
                #Registra o limite de tempo excedido para sinalizar reinícios forçados
                bound_logger.warning(
                    "limit_time_collector_exceeded",
                    uptime_seconds=round(time.monotonic() - started_at, 2),
                    reason="time_limit",
                )

                time.sleep(poll_interval)
                continue
            except SoftTimeLimitExceeded:
                #Evita encerrar a task quando o time limit suave ocorre, reiniciando o ciclo
                bound_logger.warning(
                    "continuous_soft_time_limit_exceeded",
                    uptime_seconds=round(time.monotonic() - started_at, 2),
                    reason="soft_time_limit",
                )
                time.sleep(poll_interval)
                continue
            except Exception:
                bound_logger.exception("continuous_loop_error")
                time.sleep(poll_interval)

    finally:
        release_continuous_collector_lock(owner_id=lock_owner)
            