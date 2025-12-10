""" Tarefas de monitoramento para rechecagem coordenada dos produtos.

O módulo concentra a orquestração de rechecagens: valida exclusão mútua
via flag `checking_in_progress`, executa coletas síncronas do monitorado e
de cada concorrente e dispara a comparação de preços inline quando houver
dados novos. Também expõe a task de agendamento usada pelo Beat para apenas
enfileirar rechecagens elegíveis. Locks Redis não são utilizados aqui para
evitar sobreposição com o controle transacional da flag.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import time
from uuid import UUID

import structlog
from celery.exceptions import SoftTimeLimitExceeded

from shared.infra.db import SessionLocal
from shared.metrics.metrics_scraper import (
    RECHECK_COMPETITOR_RESULT_TOTAL,
    RECHECK_MONITORED_RESULT_TOTAL,
    SCRAPING_LATENCY_SECONDS,
)
from shared.utils.redis_client import get_redis_client, is_scraping_suspended
from backend.shared.schemas.shared_schemas_scraper import ScrapeResult

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.crud.crud_competitor import get_competitors_by_monitored_id
from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.models.models_products import MonitoredProduct
from market_alert.orchestrator.collector_service import (
    build_competitor_payload,
    build_monitored_payload,
    schedule_due_monitored,
)
from market_alert.services.services_comparison import run_price_comparison
from market_alert.tasks.collector_product_task import collect_product

logger = structlog.get_logger("monitor_recheck_tasks")
redis_client = get_redis_client()


@dataclass
class CollectionOutcome:
    """ Representa o desfecho padronizado de uma coleta sincronizada """
    status: str
    reason: str | None = None
    product_id: UUID | None = None
    result: ScrapeResult | None = None

    @property
    def price_changed(self) -> bool:
        """ Informa se houve variação de preço no scrape """
        if self.result is None:
            return False
        return bool(getattr(self.result, "price_changed", False))

    @property
    def availability_changed(self) -> bool:
        """ Indica se a disponibilidade sofreu alteração """
        if self.result is None:
            return False
        return bool(getattr(self.result, "availability_changed", False))

    @property
    def has_new_data(self) -> bool:
        """Indica se houve alteração relevante que justifique comparação."""
        return bool(self.price_changed or self.availability_changed)

def _compute_next_check_at(monitored: MonitoredProduct, reference: datetime) -> datetime:
    """ Calcula o próximo agendamento de rechecagem respeitando configuração dinâmica """
    interval_seconds = getattr(monitored, "check_interval", None)
    if not isinstance(interval_seconds, int) or interval_seconds <= 0:
        interval_seconds = settings.RECHECK_INTERVAL_DEFAULT
    return reference + timedelta(seconds=interval_seconds)

def _mark_recheck_started(db: SessionLocal, monitored_id: UUID, started_at: datetime, *, logger_bound) -> bool:
    """ Marca o monitorado como em rechecagem de forma transacional """
    try:
        with db.begin():
            updated = (
                db.query(MonitoredProduct)
                .filter(
                    MonitoredProduct.id == monitored_id,
                    MonitoredProduct.checking_in_progress.is_(False),
                )
                .update(
                    {
                        "checking_in_progress": True,
                        "checking_started_at": started_at,
                    },
                    synchronize_session=False,
                )
            )
        if not updated:
            db.rollback()
            return False
    except Exception:
        db.rollback()
        logger_bound.warning("recheck_mark_failed")
        return False
    logger_bound.info("recheck_started", monitored_id=str(monitored_id), started_at=started_at.isoformat())
    return True

def _finalize_recheck_state(
    db: SessionLocal,
    monitored_id: UUID,
    *,
    last_checked: datetime | None,
    next_check_at: datetime,
) -> None:
    """ Atualiza timestamps e libera a flag de progresso de forma tolerante """
    update_payload = {
        "checking_in_progress": False,
        "checking_started_at": None,
        "next_check_at": next_check_at,
        "last_checked": last_checked,
        "last_scraped_at": last_checked,
    }
    try:
        db.query(MonitoredProduct).filter(MonitoredProduct.id == monitored_id).update(
            update_payload, synchronize_session=False
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("recheck_finalize_failed", monitored_id=str(monitored_id))

def _collect_inline(payload: dict[str, str], *, product_id: UUID, kind: str, logger_bound) -> CollectionOutcome:
    """ Executa coleta reutilizando o collector, porém sem aplicar lock Redis 
    
    Esta rotina apoia o orquestrador de monitoramento que já garante
    exclusão mútua via flag ``checking_in_progress`` em banco de dados,
    evitando a combinação de dois mecanismos de sincronização.
    """
    contextual_logger = logger_bound.bind(kind=kind) if logger_bound is not None else logger.bind(kind=kind)

    outcome, result = collect_product(
        payload,
        use_lock=False,
        dispatch_comparison=False,
        logger_bound=contextual_logger,
    )
    reason = None if outcome in {"success", "not_modified"} else outcome
    return CollectionOutcome(status=outcome, reason=reason, product_id=product_id, result=result)

@celery_app.task(
    bind=True,
    max_retries=0,
    name="market_alert.tasks.monitor_recheck_tasks.recheck_monitored_product",
    queue="monitor",
    acks_late=True,
    soft_time_limit=settings.RECHECK_TIMEOUT_SECONDS,
    time_limit=settings.RECHECK_TIMEOUT_SECONDS + 30,
)
def recheck_monitored_product(self, monitored_id: str) -> None:
    """ Orquestra rechecagem completa de um único monitorado """
    started_at = datetime.now(timezone.utc)
    task_logger = logger.bind(task_id=getattr(self.request, "id", None), monitored_id=monitored_id)

    if is_scraping_suspended():
        task_logger.warning("recheck_skipped_suspended")
        return "suspended"

    try:
        monitored_uuid = UUID(str(monitored_id))
    except Exception:
        task_logger.error("invalid_monitored_identifier")
        return "invalid_monitored_identifier"

    with SessionLocal() as db:
        monitored = get_monitored_product_by_id(db, monitored_uuid)
        if monitored is None:
            task_logger.info("recheck_skipped_missing")
            return "missing"

        if monitored.status == MonitoredStatus.failed:
            task_logger.info("recheck_skipped_failed")
            return "failed"

        if not _mark_recheck_started(db, monitored.id, started_at, logger_bound=task_logger):
            task_logger.info("recheck_already_running")
            return "already_running"
        
        previous_last_checked = monitored.last_checked
        next_check_at = _compute_next_check_at(monitored, started_at)

        try:
            monitor_payload = build_monitored_payload(monitored, user_id=monitored.user_id)
            monitor_outcome = _collect_inline(
                monitor_payload,
                product_id=monitored.id,
                kind="monitored",
                logger_bound=task_logger,
            )
            RECHECK_MONITORED_RESULT_TOTAL.labels(result=monitor_outcome.status).inc()
            task_logger.info(
                "monitor_collect_result",
                status=monitor_outcome.status,
                reason=monitor_outcome.reason,
            )

            if monitor_outcome.status not in {"success", "not_modified"}:
                _finalize_recheck_state(
                    db,
                    monitored.id,
                    last_checked=previous_last_checked,
                    next_check_at=next_check_at,
                )
                task_logger.warning("recheck_aborted", reason=monitor_outcome.reason)
                return monitor_outcome.status

            competitors = get_competitors_by_monitored_id(db, monitored.id)
            competitor_outcomes: list[CollectionOutcome] = []

            for competitor in competitors:
                competitor_payload = build_competitor_payload(competitor, user_id=monitored.user_id)
                outcome = _collect_inline(
                    competitor_payload,
                    product_id=competitor.id,
                    kind="competitor",
                    logger_bound=task_logger.bind(competitor_id=str(competitor.id)),
                )
                competitor_outcomes.append(outcome)
                RECHECK_COMPETITOR_RESULT_TOTAL.labels(result=outcome.status).inc()
                task_logger.info(
                    "competitor_collect_result",
                    status=outcome.status,
                    reason=outcome.reason,
                    competitor_id=str(competitor.id),
                )

            should_compare = (
                previous_last_checked is None
                or monitor_outcome.has_new_data
                or any(outcome.has_new_data for outcome in competitor_outcomes)
            )

            if should_compare:
                run_price_comparison(db, monitored.id)

            finished_at = datetime.now(timezone.utc)
            _finalize_recheck_state(
                db,
                monitored.id,
                last_checked=finished_at,
                next_check_at=_compute_next_check_at(monitored, finished_at),
            )
            task_logger.info(
                "recheck_finished",
                duration_ms=int((finished_at - started_at).total_seconds() * 1000),
                competitors=len(competitors),
                comparison_triggered=should_compare,
            )
            return "completed"
        
        except SoftTimeLimitExceeded:
            _finalize_recheck_state(
                db,
                monitored.id,
                last_checked=previous_last_checked,
                next_check_at=next_check_at,
            )
            task_logger.warning(
                "recheck_timeout",
                timeout_seconds=settings.RECHECK_TIMEOUT_SECONDS,
            )
            return "timeout"
        
        except Exception:
            _finalize_recheck_state(
                db,
                monitored.id,
                last_checked=previous_last_checked,
                next_check_at=next_check_at,
            )
            task_logger.exception("recheck_failed")
            raise
        finally:
            SCRAPING_LATENCY_SECONDS.labels(source="monitor_orchestrator").observe(
                (datetime.now(timezone.utc) - started_at).total_seconds()
            )


@celery_app.task(
    bind=True,
    max_retries=0,
    name="market_alert.tasks.monitor_recheck_tasks.enqueue_due_monitored",
    queue="monitor",
)
def enqueue_due_monitored(self) -> int:
    """ Agendador do Beat que apenas enfileira rechecagens elegíveis """
    started_at = time.time()
    task_logger = logger.bind(task_id=getattr(self.request, "id", None), phase="scheduler")

    if is_scraping_suspended():
        task_logger.warning("scheduler_skipped_suspended")
        SCRAPING_LATENCY_SECONDS.labels(source="monitor_scheduler").observe(time.time() - started_at)
        return 0

    with SessionLocal() as db:
        dispatched = schedule_due_monitored(db)

    SCRAPING_LATENCY_SECONDS.labels(source="monitor_scheduler").observe(time.time() - started_at)

    if redis_client is not None:
        redis_client.set(
            "beat:last_recheck",
            datetime.now(timezone.utc).isoformat(),
            ex=int(timedelta(hours=1).total_seconds()),
        )

    task_logger.info("scheduler_dispatched", dispatched=dispatched)
    return dispatched


__all__ = ["recheck_monitored_product", "enqueue_due_monitored"]
