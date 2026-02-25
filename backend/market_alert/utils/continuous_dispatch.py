""" Utilitários para despacho e reenqueue do coletor contínuo.

Centraliza a lógica de envio de tasks, decisões de requeue e reaproveitamento
de itens processados, mantendo o loop principal do worker mais enxuto e fácil
de manter.

Fila Redis acessada exclusivamente via ``CollectionQueue`` — nunca via
``PriorityQueueService`` diretamente.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

import structlog
from celery.canvas import Signature
from sqlalchemy.orm import Session

from market_alert.core.celery_app import celery_app
from market_alert.crud.crud_competitor import get_competitors_by_monitored_id
from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.models.models_products import MonitoredProduct
from market_alert.orchestrator.collector_service_orchestrator import build_competitor_payload, build_monitored_payload
from market_alert.orchestrator.collection_enqueuer import CollectionEnqueuer
from market_alert.orchestrator.collection_queue import CollectionQueue
from market_alert.utils.interval_calculator_products import (
    EVENT_RETRY,
    RetryContext,
    _resolve_next_check_at,
    _utc_now,
    calculate_schedule,
)
from market_alert.utils.rate_limiter import _resolve_cooldown_seconds


logger = structlog.get_logger("continuous_collector_utils")

@dataclass(frozen=True)
class CollectDispatchDecision:
    """ Resultado do disparo assíncrono com orientação de reenfileiramento """
    outcome: str
    next_check_at: datetime | None
    should_requeue: bool
    retain_processing: bool


def _should_abort(task_request) -> bool:
    """ Verifica se a task foi sinalizada para abortar """
    if task_request is None:
        return False
    abort_fn = getattr(task_request, "is_aborted", None)
    if abort_fn is None:
        return False
    return bool(abort_fn())


def _should_skip_requeue(monitored: MonitoredProduct, reason: str | None) -> bool:
    """ Decide se o monitorado deve ficar fora da fila após falha crítica """
    if monitored.paused or monitored.status in {MonitoredStatus.failed}:
        return True
    normalized_reason = (reason or "").strip().lower()
    return normalized_reason in {"blocked", "invalid_url_blocked"}


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
    """ Dispara coleta assíncrona delegando para CollectionEnqueuer.

    Recebe payload já serializado (dict) e delega o envio ao Celery
    exclusivamente via ``CollectionEnqueuer._send()``, mantendo um único
    ponto de chamada para ``celery_app.send_task()`` de coletas.
    """
    from market_alert.schemas.schemas_collection_payload import validate_payload as _vp
    try:
        typed_payload = _vp(payload)
        CollectionEnqueuer()._send(
            typed_payload,
            on_complete=on_complete,
            on_error=on_error,
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
    db: Session,
    monitored: MonitoredProduct,
    enqueued_at: datetime | None,
) -> CollectDispatchDecision:
    """ Dispara coletas do monitorado e concorrentes retornando decisão de reenqueue """
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

    #Builders retornam CollectionPayload tipado — serializa para dict ao enviar para Celery
    monitored_payload = build_monitored_payload(
        monitored,
        user_id=monitored.user_id,
        enqueued_at=enqueued_at.isoformat() if enqueued_at else None,
        trace_id=trace_id,
    )

    competitors = get_competitors_by_monitored_id(
        db,
        monitored.id,
        include_paused=False,
        include_inactive=True, #Inclui itens indisponíveis para rechecagem
    )

    monitored_enqueued = _dispatch_collect_task(
        payload=monitored_payload.model_dump(mode="json"),
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
        cooldown_seconds = _resolve_cooldown_seconds(str(competitor.id))
        if cooldown_seconds is not None:
            logger.info(
                "continuous_competitor_cooldown_active",
                monitored_id=str(monitored.id),
                competitor_id=str(competitor.id),
                cooldown_seconds=cooldown_seconds,
                trace_id=trace_id,
            )
            continue
        competitor_payload = build_competitor_payload(
            competitor,
            user_id=monitored.user_id,
            enqueued_at=enqueued_at.isoformat() if enqueued_at else None,
            trace_id=trace_id,
        )
        dispatched = _dispatch_collect_task(
            payload=competitor_payload.model_dump(mode="json"),
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
    queue: CollectionQueue,
) -> tuple[bool, datetime]:
    """ Reenfileira monitorado via CollectionQueue e informa se houve sucesso.

    Tenta reenfileirar com o ``next_check_at`` calculado. Se falhar,
    tenta novamente com timestamp imediato para minimizar impacto transitório.
    """
    #Usa a janela calculada pela coleta para garantir o reenqueue correto
    resolved_next_check_at, now = _resolve_next_check_at(monitored, next_check_at)
    if queue.reenqueue_after_collection(
        monitored.id,
        resolved_next_check_at,
        source="continuous_worker",
    ):
        return True, resolved_next_check_at

    logger.error(
        "continuous_requeue_failed",
        monitored_id=str(monitored.id),
        next_check_at=resolved_next_check_at.isoformat(),
    )
    #Tenta reenfileirar imediatamente para minimizar impacto de falhas transitórias
    if queue.reenqueue_after_collection(
        monitored.id,
        now,
        source="continuous_worker",
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


def _handle_processing_requeue(
    *,
    db: Session,
    monitored_id: str,
    collect_outcome: str | None,
    reason: str,
    trace_id: str | None = None,
    next_retry_at: datetime | None = None,
) -> None:
    """ Conclui o fluxo de processamento movendo o item de volta para o ready.

    Fila Redis acessada via ``CollectionQueue`` — nunca diretamente.
    """
    queue = CollectionQueue()
    normalized_reason = reason or collect_outcome or "unknown"
    normalized_outcome = (collect_outcome or "").strip().lower()

    #Nos desfechos de sucesso, o collector já persiste `next_check_at`` no CRUD.
    #Reusar esse valor evita recalcular janela e preserva o contrato de estabilidade.
    success_without_explicit_retry = (
        normalized_outcome in {"success", "not_modified"}
        and next_retry_at is None
    )

    monitored = _load_monitored(db, monitored_id)
    if monitored is None:
        logger.warning(
            "continuous_processing_missing",
            monitored_id=monitored_id,
            reason="monitored_missing",
            trace_id=trace_id,
        )
        queue.mark_as_done([monitored_id])
        return

    if _should_skip_requeue(monitored, normalized_reason):
        try:
            queue.remove_from_collection(UUID(monitored_id), source="continuous_requeue_blocked")
        except Exception:
            queue.mark_as_done([monitored_id])
        logger.warning(
            "continuous_processing_blocked",
            monitored_id=monitored_id,
            reason=normalized_reason,
            status=monitored.status,
            trace_id=trace_id,
        )
        return

    schedule_reason: str
    schedule_source: str
    if success_without_explicit_retry:
        scheduling_next_check_at, _ = _resolve_next_check_at(monitored, monitored.next_check_at)
        schedule_reason = "persisted_next_check_at"
        schedule_source = "requeue_from_persisted_schedule"
    else:
        resolved_next_check_at, now = _resolve_next_check_at(monitored, next_retry_at)
        scheduling = calculate_schedule(
            monitored,
            reference_time=now,
            event_type=EVENT_RETRY,
            retry_context=RetryContext(
                reason=normalized_reason,
                next_retry_at=resolved_next_check_at,
            ),
        )
        scheduling_next_check_at = scheduling.next_check_at
        schedule_reason = scheduling.reason
        schedule_source = "requeue_from_retry_policy"

    requeued, effective_next_check_at = _requeue_monitored(
        monitored=monitored,
        next_check_at=scheduling_next_check_at,
        queue=queue,
    )

    if requeued:
        queue.mark_as_done([monitored_id])
        logger.info(
            "continuous_processing_returned_to_ready",
            monitored_id=monitored_id,
            next_check_at=effective_next_check_at.isoformat(),
            reason=normalized_reason,
            schedule_reason=schedule_reason,
            schedule_source=schedule_source,
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


__all__ = [
    "CollectDispatchDecision",
    "_should_abort",
    "_should_skip_requeue",
    "_dispatch_collect_task",
    "_collect_group",
    "_handle_processing_requeue",
    "_load_monitored",
    "_requeue_monitored",
]
