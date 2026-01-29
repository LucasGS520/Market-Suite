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
from celery.exceptions import SoftTimeLimitExceeded

from shared.infra.db import SessionLocal
from shared.metrics.metrics_priority_queue import (
    CONTINUOUS_COLLECTOR_SOFT_TIMEOUTS_TOTAL,
    PRIORITY_QUEUE_CONSUME_LATENCY_MS,
    PRIORITY_QUEUE_LOOP_ERRORS_TOTAL,
    PRIORITY_QUEUE_PROCESSED_TOTAL,
    PRIORITY_QUEUE_FAILED_BUT_RETAINED_TOTAL,
    PRIORITY_QUEUE_READY_TOTAL,
    PRIORITY_QUEUE_SIZE,
    PRIORITY_QUEUE_STABILITY_TOTAL,
)
from shared.metrics.metrics_products import COMPETITOR_CHANGE_AFFECTED_STABILITY_TOTAL
from shared.metrics.metrics_scraper import (
    COMPETITOR_COLLECT_DURATION_MS,
    COMPETITOR_COLLECT_IN_FLIGHT,
    COMPETITOR_COLLECT_OUTCOME_TOTAL,
    CONTINUOUS_COMPETITOR_PARSE_FAILURE_TOTAL,
    CONTINUOUS_COMPETITOR_SKIPPED_TOTAL,
    MONITORED_SKIPPED_PAUSED_TOTAL,
)
from shared.utils.redis_client import is_scraping_suspended

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.crud.crud_competitor import get_competitors_by_monitored_id
from market_alert.crud.crud_monitored import get_monitored_product_by_id, get_last_price_change_for_monitored
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.models.models_products import MonitoredProduct
from market_alert.orchestrator.collector_service_orchestrator import build_monitored_payload, build_competitor_payload
from market_alert.services.services_priority_queue import PriorityQueueService
from market_alert.services.services_priority_queue_manager import enqueue_monitored_at
from market_alert.tasks.collector_product_task import collect_product
from market_alert.utils.interval_calculator_products import (
    calculate_next_check_at,
    calculate_stability_score,
    STABILITY_STABLE,
    STABILITY_UNSTABLE,
    STABILITY_VERY_STABLE,
)
from backend.shared.schemas.shared_schemas_scraper import ScrapeResult


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

def _collect_group(
    *,
    monitored: MonitoredProduct,
    enqueued_at: datetime | None,
) -> tuple[str, datetime | None]:
    """ Coleta monitorado e concorrentes e retorna desfecho e próxima rechecagem """
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
                return "skipped_paused", None
            #Mantém os dados atualizados para o restante do processamento
            db.expunge(refreshed)
            monitored = refreshed

    trace_id = str(uuid4())
    group_started_at = _utc_now()
    group_started_perf = time.perf_counter()
    next_check_at: datetime | None = None

    if monitored.paused or monitored.status in {MonitoredStatus.failed}:
        #Evita coletas em itens pausados para respeitar contrato de pausa
        logger.info(
            "continuous_group_skipped_paused",
            monitored_id=str(monitored.id),
            status=monitored.status,
        )
        return "skipped_paused", None
    
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
        #Usa uma sessão compartilhada para manter commits e refresh no mesmo contexto
        try:
            outcome, monitored_result = collect_product(
                monitored_payload,
                use_lock=True,
                dispatch_comparison=False,
                logger_bound=logger.bind(monitored_id=str(monitored.id), trace_id=trace_id),
                db=db,
            )
        except Exception:
            #Mantém o loop vivo ao capturar falhas inesperadas do coletor do monitorado
            logger.exception(
                "continuous_monitored_collect_failed",
                monitored_id=str(monitored.id),
                trace_id=trace_id,
            )
            outcome, monitored_result = "error", None

        competitors = get_competitors_by_monitored_id(
            db,
            monitored.id,
            include_paused=False,
            include_inactive=True, #Inclui itens indisponíveis para rechecagem
        )
        competitor_change_detected = False
        for competitor in competitors:
            db.refresh(competitor)
            previous_change_at = competitor.last_price_change_at
            competitor_started_perf = time.perf_counter()
            competitor_payload = build_competitor_payload(
                competitor,
                user_id=monitored.user_id,
                enqueued_at=enqueued_at.isoformat() if enqueued_at else None,
            )
            competitor_payload["trace_id"] = trace_id
            try:
                COMPETITOR_COLLECT_IN_FLIGHT.inc()
                competitor_outcome, competitor_result = collect_product(
                    competitor_payload,
                    use_lock=True,
                    dispatch_comparison=False,
                    logger_bound=logger.bind(
                        monitored_id=str(monitored.id),
                        competitor_id=str(competitor.id),
                        trace_id=trace_id,
                    ),
                    db=db,
                )
            except Exception:
                #Isola falhas de concorrentes para não comprometer grupo inteiro
                logger.exception(
                    "continuous_competitor_collect_failed",
                    monitored_id=str(monitored.id),
                    competitor_id=str(competitor.id),
                    trace_id=trace_id,
                )
                competitor_outcome, competitor_result = "error", None
            finally:
                #Mantém o gauge consistente mesmo quando ocorrem falhas inesperadas
                COMPETITOR_COLLECT_IN_FLIGHT.dec()
                competitor_duration_ms = int(
                    (time.perf_counter() - competitor_started_perf) * 1000
                )
                COMPETITOR_COLLECT_DURATION_MS.observe(competitor_duration_ms)
            _record_competitor_metrics(
                outcome=competitor_outcome,
                result=competitor_result,
                monitored_id=str(monitored.id),
                competitor_id=str(competitor.id),
                trace_id=trace_id,
            )
            db.refresh(competitor)
            if competitor.last_price_change_at != previous_change_at:
                competitor_change_detected = True
            logger.info(
                "continuous_competitor_collected",
                monitored_id=str(monitored.id),
                competitor_id=str(competitor.id),
                duration_ms=competitor_duration_ms,
                trace_id=trace_id,
            )

        group_finished_at = _utc_now()
        refreshed = get_monitored_product_by_id(db, monitored.id)
        if refreshed:
            refreshed.group_collected_at = group_finished_at
            refreshed.last_price_change_at = get_last_price_change_for_monitored(
                db,
                refreshed.id,
            )
            if competitor_change_detected:
                #Reduzimos estabilidade para acelerar novas coletas após mudanças do concorrente.
                refreshed.stability_score = STABILITY_UNSTABLE
                COMPETITOR_CHANGE_AFFECTED_STABILITY_TOTAL.inc()
                logger.info(
                    "monitored_stability_reset_by_competitor",
                    monitored_id=str(refreshed.id),
                    collected_at=group_finished_at.isoformat(),
                )
            else:
                refreshed.stability_score = calculate_stability_score(
                    refreshed,
                    reference_time=group_finished_at,
                )
            refreshed.next_check_at = calculate_next_check_at(
                refreshed,
                collected_at=group_finished_at,
            )
            next_check_at = refreshed.next_check_at
            if next_check_at is None or next_check_at < group_finished_at:
                #Protege o reenque com um timestamp válido para manter a fila ativa
                next_check_at = group_finished_at
                refreshed.next_check_at = next_check_at
            db.commit()

    if monitored_result and monitored_result.status:
        PRIORITY_QUEUE_PROCESSED_TOTAL.labels(source="continuous", outcome=monitored_result.status).inc()
    else:
        PRIORITY_QUEUE_PROCESSED_TOTAL.labels(source="continuous", outcome=outcome).inc()

    if monitored_result is not None:
        has_change = bool(
            getattr(monitored_result, "price_changed", False)
            or getattr(monitored_result, "availability_changed", False)
        )
    else:
        has_change = False

    if has_change or competitor_change_detected:
        #Dispara comparação apenas uma vez após coletar todo o grupo
        celery_app.send_task(
            "market_alert.tasks.compare_prices_task.compare_prices_task",
            args=[
                str(monitored.id),
                bool(getattr(monitored_result, "price_changed", False)) if monitored_result else False,
                bool(getattr(monitored_result, "availability_changed", False)) if monitored_result else False,
                trace_id,
            ],
            queue="monitor",
        )

    group_duration_ms = int((time.perf_counter() - group_started_perf) * 1000)
    logger.info(
        "continuous_group_finished",
        monitored_id=str(monitored.id),
        duration_ms=group_duration_ms,
        trace_id=trace_id,
    )

    if next_check_at is None:
        #Garante que o reagendamento sempre tenha base temporal válida
        next_check_at = _utc_now()

    return outcome, next_check_at

def _record_competitor_metrics(
    *,
    outcome: str,
    result: ScrapeResult | None,
    monitored_id: str,
    competitor_id: str,
    trace_id: str,
) -> None:
    """ Registra métricas específicas de concorrentes processados no loop contínuo """
    outcome_label = _resolve_competitor_outcome_label(outcome=outcome, result=result)
    if outcome_label:
        COMPETITOR_COLLECT_OUTCOME_TOTAL.labels(outcome=outcome_label).inc()
    
    if result is None:
        if outcome == "error":
            CONTINUOUS_COMPETITOR_PARSE_FAILURE_TOTAL.inc()
        return
    
    if result.error_code == "lock_skipped":
        CONTINUOUS_COMPETITOR_SKIPPED_TOTAL.labels(reason="lock").inc()
        logger.info(
            "continuous_competitor_skipped_lock",
            monitored_id=monitored_id,
            competitor_id=competitor_id,
            trace_id=trace_id,
        )
        return

    if result.error_code == "paused":
        CONTINUOUS_COMPETITOR_SKIPPED_TOTAL.labels(reason="paused").inc()
        logger.info(
            "continuous_competitor_skipped_paused",
            monitored_id=monitored_id,
            competitor_id=competitor_id,
            trace_id=trace_id,
        )
        return
    
    if result.status == "no_result" and result.error_code == "no_result":
        CONTINUOUS_COMPETITOR_PARSE_FAILURE_TOTAL.inc()
        logger.info(
            "continuous_competitor_parse_failure",
            monitored_id=monitored_id,
            competitor_id=competitor_id,
            trace_id=trace_id,
        )

def _resolve_competitor_outcome_label(
    *,
    outcome: str,
    result: ScrapeResult | None,
) -> str | None:
    """ Normaliza o label de desfecho de concorrentes para métricas consolidadas """
    if result is None:
        return "error" if outcome == "error" else None
    if result.error_code == "lock_skipped":
        return "lock_skipped"
    if result.status in {"success", "not_modified", "no_result", "error"}:
        return result.status
    if outcome in {"success", "not_modified", "no_result", "error"}:
        return outcome
    return None

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
    queue_service = PriorityQueueService()
    batch_size = max(1, int(settings.CONTINUOUS_WORKER_BATCH_SIZE))
    processing_ttl = int(settings.CONTINUOUS_WORKER_PROCESSING_TTL_SECONDS)
    poll_interval = float(settings.CONTINUOUS_WORKER_POLL_INTERVAL)

    while True:
        processed_ids: list[str] = []
        if _should_abort(getattr(self, "request", None)):
            bound_logger.warning("continuous_worker_aborted")
            return
        
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
                    outcome, next_check_at = _collect_group(
                        monitored=monitored,
                        enqueued_at=enqueued_at,
                    )
                except Exception:
                    outcome, next_check_at = "error", None
                    PRIORITY_QUEUE_LOOP_ERRORS_TOTAL.labels(source="continuous").inc()
                    bound_logger.exception(
                        "continuous_group_failed",
                        monitored_id=str(monitored.id),
                    )

                processed_ids.append(str(monitored.id))

                if outcome != "skipped_paused":
                    requeue_success = _requeue_monitored(
                        monitored=monitored,
                        next_check_at=next_check_at,
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
                    outcome=outcome,
                )

            if processed_ids:
                _drain_processing(queue_service, processed_ids)
                with SessionLocal() as db:
                    _update_stability_metrics(db)
                _update_queue_metrics(queue_service)
            time.sleep(poll_interval)
        except SoftTimeLimitExceeded:
            #Evita encerrar a task quando o time limit suave ocorre, reiniciando o ciclo
            CONTINUOUS_COLLECTOR_SOFT_TIMEOUTS_TOTAL.inc()
            bound_logger.warning(
                "continuous_soft_time_limit_exceeded",
                restart="scheduled",
            )
            time.sleep(poll_interval)
            continue
        except Exception:
            PRIORITY_QUEUE_LOOP_ERRORS_TOTAL.labels(source="continuous").inc()
            bound_logger.exception("continuous_loop_error")
            time.sleep(poll_interval)
            