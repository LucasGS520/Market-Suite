""" Worker contínuo para consumo da fila de prioridade de monitorados

Este módulo implementa um loop dedicado que consulta a fila ordenada em Redis,
executa a coleta do monitorado e de seus concorrentes em sequência e recalcula
as janelas de rechecagem com base na estabilidade observada.

Fila Redis acessada exclusivamente via ``CollectionQueue`` — nunca via
``PriorityQueueService`` diretamente.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from billiard.exceptions import TimeLimitExceeded
from celery.exceptions import SoftTimeLimitExceeded

from shared.infra.db import SessionLocal
from shared.utils.redis_client import is_scraping_suspended
from shared.utils.redis_locks import (
    acquire_continuous_collector_lock,
    refresh_continuous_collector_lock,
    release_continuous_collector_lock,
)

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.orchestrator.collection_queue import CollectionQueue
from market_alert.utils.continuous_dispatch import (
    CollectDispatchDecision,
    _collect_group,
    _handle_processing_requeue,
    _load_monitored,
    _requeue_monitored,
    _should_abort,
)
from market_alert.utils.interval_calculator_products import _parse_next_retry_at, _utc_now
from market_alert.utils.collector_result import _parse_collect_result


logger = structlog.get_logger("continuous_collector_task")


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
    """Reenfileira monitorado quando a task de coleta falha inesperadamente."""
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
    """ Loop contínuo que consome a fila de prioridade e dispara coletas.

    Faz polling em intervalo fixo para garantir consumo contínuo sem pausas
    progressivas, mantendo o worker ativo 24/7. Esta task é contínua e não
    deve herdar hard time limit para evitar encerramento forçado do worker.

    A fila Redis é acessada exclusivamente via ``CollectionQueue``.
    """
    bound_logger = logger.bind(task_id=getattr(self.request, "id", None))
    started_at = time.monotonic()
    queue = CollectionQueue()
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

                if not queue.is_available():
                    bound_logger.error("continuous_queue_unavailable")
                    time.sleep(poll_interval)
                    continue

                queue_size = queue.size()
                ready_total = queue.ready_count()

                #Mantém um log por ciclo enquanto o lock está válido
                bound_logger.info(
                    "continuous_loop_iteration",
                    queue_size=queue_size,
                    ready_total=ready_total,
                    timestamp=_utc_now().isoformat(),
                )

                reclaimed = queue.reclaim_stale_items(processing_ttl)
                if reclaimed:
                    #Recoloca itens travados para garantir novas tentativas no loop contínuo
                    bound_logger.warning(
                        "continuous_processing_reclaimed",
                        reclaimed_count=len(reclaimed),
                    )

                for _ in range(batch_size):
                    next_id = queue.pop_next_for_collection()
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

                    enqueued_at = queue.get_enqueued_at(next_id)
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
                            queue=queue,
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
                    queue.mark_as_done(processed_ids)
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
