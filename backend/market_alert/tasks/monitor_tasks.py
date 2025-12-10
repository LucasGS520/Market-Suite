""" Tarefas de monitoramento para rechecagem coordenada dos produtos.

O módulo concentra a orquestração de rechecagens: valida exclusão mútua
via flag `checking_in_progress`, executa coletas síncronas do monitorado e
de cada concorrente e dispara a comparação de preços inline quando houver
dados novos. Também expõe a task de agendamento usada pelo Beat para apenas
enfileirar rechecagens elegíveis.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import time
from uuid import UUID

import structlog
from celery.exceptions import SoftTimeLimitExceeded

from shared.exceptions import ScraperError
from shared.infra.db import SessionLocal
from shared.metrics.metrics_scraper import (
    COLLECTOR_LOCK_ACQUIRED_TOTAL,
    COLLECTOR_LOCK_SKIPPED_TOTAL,
    RECHECK_COMPETITOR_RESULT_TOTAL,
    RECHECK_MONITORED_RESULT_TOTAL,
    SCRAPING_LATENCY_SECONDS,
)
from shared.utils.redis_client import get_redis_client, is_scraping_suspended
from shared.utils.redis_locks import acquire_product_lock, release_product_lock
from backend.shared.schemas.shared_schemas_products import (
    CompetitorProductCreateScraping,
    MonitoredProductCreateScraping,
)
from backend.shared.schemas.shared_schemas_scraper import ScrapeResult

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.crud.crud_competitor import get_competitors_by_monitored_id
from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.models.models_products import MonitoredProduct
from market_alert.orchestrator.collector_services import schedule_due_monitored
from market_alert.services.services_comparison import run_price_comparison
from market_alert.services.services_scraper_competitor import scrape_competitor_product
from market_alert.services.services_scraper_monitored import scrape_monitored_product

logger = structlog.get_logger("monitor_tasks")
redis_client = get_redis_client()


@dataclass
class CollectionOutcome:
    """ Representa o desfecho padronizado de uma coleta sincronizada """
    status: str
    reason: str | None = None
    product_id: UUID | None = None
    price_changed: bool = False
    availability_changed: bool = False

    @property
    def has_new_data(self) -> bool:
        """ Indica se houve alteração relevante que justifique comparação """
        return self.status == "success"

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

def _normalize_result(status: ScrapeResult, product_id: UUID, *, logger_bound) -> CollectionOutcome:
    """Traduz ``ScrapeResult`` em ``CollectionOutcome`` para o orquestrador."""
    if status.status == "no_result":
        return CollectionOutcome(status="no_result", reason="no_result", product_id=product_id)

    if status.status == "not_modified":
        return CollectionOutcome(status="not_modified", reason="not_modified", product_id=product_id)

    if status.status != "success":
        logger_bound.warning("collect_failed", reason=status.status)
        return CollectionOutcome(status="error", reason=status.status, product_id=product_id)

    changed = bool(getattr(status, "price_changed", False) or getattr(status, "availability_changed", False))
    normalized_status = "success" if changed else "not_modified"
    return CollectionOutcome(
        status=normalized_status,
        reason=None,
        product_id=product_id,
        price_changed=getattr(status, "price_changed", False),
        availability_changed=getattr(status, "availability_changed", False),
    )

def _collect_with_lock(product_id: UUID, kind: str, collector, *, logger_bound) -> CollectionOutcome:
    """ Encapsula aquisição/liberação de lock Redis ao executar scraping """
    lock_acquired = acquire_product_lock(product_id)
    if not lock_acquired:
        COLLECTOR_LOCK_SKIPPED_TOTAL.labels(kind=kind).inc()
        return CollectionOutcome(status="skipped_lock", reason="lock_not_acquired", product_id=product_id)

    COLLECTOR_LOCK_ACQUIRED_TOTAL.labels(kind=kind).inc()
    try:
        return collector()
    finally:
        release_product_lock(product_id)

def _collect_monitored_single(db: SessionLocal, monitored: MonitoredProduct, *, logger_bound) -> CollectionOutcome:
    """ Executa coleta do monitorado utilizando o serviço síncrono de scraping """
    def _collector() -> CollectionOutcome:
        payload = MonitoredProductCreateScraping(
            name_identification=monitored.name_identification,
            product_url=monitored.product_url,
        )
        result: ScrapeResult = scrape_monitored_product(
            db=db,
            url=monitored.product_url,
            user_id=monitored.user_id,
            payload=payload,
        )
        return _normalize_result(result, monitored.id, logger_bound=logger_bound)
    
    try:
        return _collect_with_lock(monitored.id, "monitored", _collector, logger_bound=logger_bound)
    except ScraperError as exc:
        logger_bound.warning("monitored_collect_error", error=str(exc))
        return CollectionOutcome(status="error", reason="scraper_error", product_id=monitored.id)
    except Exception:
        logger_bound.exception("monitored_collect_unexpected")
        return CollectionOutcome(status="error", reason="unexpected", product_id=monitored.id)

def _collect_competitor_single(db: SessionLocal, competitor, user_id: UUID, *, logger_bound) -> CollectionOutcome:
    """ Executa coleta de concorrente isoladamente, sem interromper o fluxo principal """
    def _collector() -> CollectionOutcome:
        payload = CompetitorProductCreateScraping(
            monitored_product_id=competitor.monitored_product_id,
            product_url=competitor.product_url,
        )
        result: ScrapeResult = scrape_competitor_product(
            db=db,
            user_id=user_id,
            url=competitor.product_url,
            payload=payload,
        )
        return _normalize_result(result, competitor.id, logger_bound=logger_bound)
    
    try:
        return _collect_with_lock(competitor.id, "competitor", _collector, logger_bound=logger_bound)
    except ScraperError as exc:
        logger_bound.warning("competitor_collect_error", error=str(exc))
        return CollectionOutcome(status="error", reason="scraper_error", product_id=competitor.id)
    except Exception:
        logger_bound.exception("competitor_collect_unexpected")
        return CollectionOutcome(status="error", reason="unexpected", product_id=competitor.id)
    

@celery_app.task(
    bind=True,
    max_retries=0,
    name="market_alert.tasks.monitor_tasks.recheck_monitored_product",
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
            monitor_outcome = _collect_monitored_single(db, monitored, logger_bound=task_logger)
            RECHECK_MONITORED_RESULT_TOTAL.labels(result=monitor_outcome.status).inc()
            task_logger.info(
                "monitor_collect_result",
                status=monitor_outcome.status,
                reason=monitor_outcome.reason,
            )

            if monitor_outcome.status in {"error", "no_result", "skipped_lock"}:
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
                outcome = _collect_competitor_single(
                    db,
                    competitor,
                    monitored.user_id,
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
    name="market_alert.tasks.monitor_tasks.enqueue_due_monitored",
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
