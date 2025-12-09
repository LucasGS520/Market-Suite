""" Task centralizada de coleta para monitorados e concorrentes.

O módulo mantém uma única tarefa Celery que executa o scraping
do item solicitado e delega o pós-processamento para os serviços
existentes, disparando coletas de concorrentes vinculados e
comparações quando necessário.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping
from uuid import UUID

import structlog
from celery import shared_task
from sqlalchemy.orm import Session

from shared.exceptions import ScraperError
from shared.infra.db import SessionLocal
from shared.metrics.metrics_scraper import (
    COLLECTOR_ERROR_TOTAL,
    COLLECTOR_LOCK_ACQUIRED_TOTAL,
    COLLECTOR_LOCK_SKIPPED_TOTAL,
    COLLECTOR_NO_DATA_TOTAL,
    COLLECTOR_SUCCESS_NEW_DATA_TOTAL,
    COLLECTOR_SUCCESS_NO_CHANGE_TOTAL,
    SCRAPER_IN_FLIGHT,
)
from shared.utils.redis_client import is_scraping_suspended
from shared.utils.redis_locks import acquire_product_lock, release_product_lock
from shared.enums.error_codes import ScrapingErrorType

from backend.shared.schemas.shared_schemas_products import (
    CompetitorProductCreateScraping,
    MonitoredProductCreateScraping,
)
from backend.shared.schemas.shared_schemas_scraper import ScrapeResult
from market_alert.core.config_alert import settings
from market_alert.core.celery_app import celery_app
from market_alert.crud import crud_errors
from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.services.collector_services import enqueue_competitors_for_monitored
from market_alert.services.services_scraper_competitor import scrape_competitor_product
from market_alert.services.services_scraper_monitored import scrape_monitored_product
from market_alert.tasks.compare_prices_tasks import compare_prices_task
from market_alert.utils.rate_limiter import allow_with_leaky_bucket, parse_rate_limit_config


logger = structlog.get_logger("collector_tasks")

@celery_app.task(
    bind=True,
    max_retries=0,
    name="market_alert.tasks.collector_tasks.collect_product_task",
    queue="scraping",
    acks_late=True,
)
def collect_product_task(self, payload: Mapping[str, str] | None = None) -> None:
    """ Coleta produto monitorado ou concorrente e agenda pós-processamentos """
    SCRAPER_IN_FLIGHT.inc()
    start = datetime.now(timezone.utc)
    task_logger = logger.bind(task_id=self.request.id)

    if payload is None:
        SCRAPER_IN_FLIGHT.dec()
        task_logger.error("missing_payload")
        return

    target_kind = payload.get("kind", "monitored")
    lock_id = payload.get("competitor_id") or payload.get("monitored_id")
    lock_acquired = False

    if lock_id:
        lock_acquired = acquire_product_lock(lock_id)
        if lock_acquired:
            COLLECTOR_LOCK_ACQUIRED_TOTAL.labels(kind=target_kind).inc()
        else:
            COLLECTOR_LOCK_SKIPPED_TOTAL.labels(kind=target_kind).inc()
            SCRAPER_IN_FLIGHT.dec()
            task_logger.warning("collect_skipped_lock", kind=target_kind, product_id=lock_id)
            return
        
    monitored_id: UUID | None = None
    competitor_id: UUID | None = None

    try:
        if target_kind == "competitor":
            outcome, reason, monitored_id, competitor_id = _process_competitor(task_logger, payload)
        else:
            outcome, reason, monitored_id, competitor_id = _process_monitored(task_logger, payload)
        _record_outcome(
            kind=target_kind,
            outcome=outcome,
            reason=reason,
            task_logger=task_logger,
            monitored_id=monitored_id,
            competitor_id=competitor_id,
        )
    except Exception as exc:
        COLLECTOR_ERROR_TOTAL.labels(kind=target_kind).inc()
        task_logger.exception("collect_product_failed", kind=target_kind, error=str(exc))
            
    finally:
        if lock_id and lock_acquired:
            release_product_lock(lock_id)
        SCRAPER_IN_FLIGHT.dec()
        elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        task_logger.info(
            "collect_product_finished",
            kind=target_kind,
            duration_ms=elapsed_ms,
            outcome=locals().get("outcome"),
            product_id=str(competitor_id or monitored_id) if (competitor_id or monitored_id) else None,
            monitored_id=str(monitored_id) if monitored_id else None,
            competitor_id=str(competitor_id) if competitor_id else None,
        )


def _process_monitored(
    task_logger,
    payload: Mapping[str, str],
) -> tuple[str, str | None, UUID | None, UUID | None]:
    """ Executa coleta de monitorado e enfileira concorrentes associados """
    monitored_id: UUID | None = None
    if is_scraping_suspended():
        task_logger.warning("scraping_suspended")
        COLLECTOR_NO_DATA_TOTAL.labels(kind="monitored").inc()
        return "no_data", "scraping_suspended", monitored_id, None

    try:
        monitored_id = UUID(str(payload["monitored_id"]))
        user_id = UUID(str(payload["user_id"]))
    except Exception as exc:
        task_logger.error("invalid_monitored_reference", error=str(exc))
        COLLECTOR_ERROR_TOTAL.labels(kind="monitored").inc()
        return "error", "invalid_reference", monitored_id, None

    product_url = payload.get("url")
    name_identification = payload.get("name")

    parsed_limit = parse_rate_limit_config(settings.SCRAPER_RATE_LIMIT)
    if parsed_limit:
        bucket_key = f"rate:scrape:{user_id}"
        if not allow_with_leaky_bucket(bucket_key, rate_limit=parsed_limit):
            task_logger.warning("monitored_rate_limit", monitored_id=str(monitored_id))
            COLLECTOR_NO_DATA_TOTAL.labels(kind="monitored").inc()
            return "no_data", "rate_limited", monitored_id, None

    payload_model = MonitoredProductCreateScraping(
        product_url=product_url,
        name_identification=name_identification,
    )

    with SessionLocal() as db:
        return (
            *_run_monitored_scrape(db, task_logger, monitored_id, user_id, payload_model),
            monitored_id,
            None,
        )


def _run_monitored_scrape(
    db: Session,
    task_logger,
    monitored_id: UUID,
    user_id: UUID,
    payload: MonitoredProductCreateScraping,
) -> tuple[str, str | None]:
    """ Fluxo síncrono de scraping de monitorados com comparação condicional """
    try:
        result: ScrapeResult = scrape_monitored_product(
            db=db,
            url=str(payload.product_url),
            user_id=user_id,
            payload=payload,
        )
    except ScraperError as exc:
        task_logger.warning("scraper_error", error=str(exc))
        _register_error(db, monitored_id, str(payload.product_url), str(exc), ScrapingErrorType.parsing_error)
        COLLECTOR_ERROR_TOTAL.labels(kind="monitored").inc()
        return "error", "scraper_error"
    except Exception as exc:
        task_logger.exception("unexpected_monitored_error")
        _register_error(db, monitored_id, str(payload.product_url), str(exc), ScrapingErrorType.parsing_error)
        COLLECTOR_ERROR_TOTAL.labels(kind="monitored").inc()
        return "error", "unexpected"

    if result.status == "no_result":
        COLLECTOR_NO_DATA_TOTAL.labels(kind="monitored").inc()
        _register_error(db, monitored_id, str(payload.product_url), "no_result", ScrapingErrorType.parsing_error)
        return "no_data", "no_result"

    if getattr(result, "price_changed", False) or getattr(result, "availability_changed", False):
        compare_prices_task.apply_async(args=[str(monitored_id)], queue="monitor")
        COLLECTOR_SUCCESS_NEW_DATA_TOTAL.labels(kind="monitored").inc()
        enqueue_competitors_for_monitored(db, monitored_id)
        return "new_data", None

    enqueue_competitors_for_monitored(db, monitored_id)
    COLLECTOR_SUCCESS_NO_CHANGE_TOTAL.labels(kind="monitored").inc()
    return "no_change", "not_modified"

def _process_competitor(
    task_logger,
    payload: Mapping[str, str],
) -> tuple[str, str | None, UUID | None, UUID | None]:
    """ Executa coleta de concorrente e dispara comparação do monitorado """
    monitored_id: UUID | None = None
    competitor_id: UUID | None = None
    if is_scraping_suspended():
        task_logger.warning("scraping_suspended")
        COLLECTOR_NO_DATA_TOTAL.labels(kind="competitor").inc()
        return "no_data", "scraping_suspended", monitored_id, competitor_id

    try:
        monitored_id = UUID(str(payload["monitored_id"]))
        competitor_id_value = payload.get("competitor_id")
        competitor_id = UUID(str(competitor_id_value)) if competitor_id_value else None
    except Exception as exc:
        task_logger.error("invalid_monitored_reference", error=str(exc))
        COLLECTOR_ERROR_TOTAL.labels(kind="competitor").inc()
        return "error", "invalid_reference", monitored_id, competitor_id

    user_id = payload.get("user_id")
    user_uuid = UUID(str(user_id)) if user_id else None
    product_url = payload.get("url")

    payload_model = CompetitorProductCreateScraping(
        monitored_product_id=monitored_id,
        product_url=product_url,
    )

    with SessionLocal() as db:
        return (
            *_run_competitor_scrape(db, task_logger, monitored_id, user_uuid, payload_model),
            monitored_id,
            competitor_id,
        )


def _run_competitor_scrape(
    db: Session,
    task_logger,
    monitored_id: UUID,
    user_id: UUID | None,
    payload: CompetitorProductCreateScraping,
) -> tuple[str, str | None]:
    """ Fluxo síncrono de scraping de concorrentes com comparação automática """
    resolved_user = user_id
    if resolved_user is None:
        monitored = get_monitored_product_by_id(db, monitored_id)
        resolved_user = monitored.user_id if monitored else UUID(int=0)

    try:
        result: ScrapeResult = scrape_competitor_product(
            db=db,
            user_id=resolved_user,
            url=str(payload.product_url),
            payload=payload,
        )
    except ScraperError as exc:
        task_logger.warning("scraper_error", error=str(exc))
        _register_error(db, monitored_id, str(payload.product_url), str(exc), ScrapingErrorType.parsing_error)
        COLLECTOR_ERROR_TOTAL.labels(kind="competitor").inc()
        return "error", "scraper_error"
    except Exception as exc:
        task_logger.exception("unexpected_competitor_error")
        _register_error(db, monitored_id, str(payload.product_url), str(exc), ScrapingErrorType.parsing_error)
        COLLECTOR_ERROR_TOTAL.labels(kind="competitor").inc()
        return "error", "unexpected"


    if result.status == "no_result":
        COLLECTOR_NO_DATA_TOTAL.labels(kind="competitor").inc()
        _register_error(db, monitored_id, str(payload.product_url), "no_result", ScrapingErrorType.parsing_error)
        return "no_data", "no_result"

    if getattr(result, "price_changed", False) or getattr(result, "availability_changed", False):
        compare_prices_task.apply_async(args=[str(monitored_id)], queue="monitor")
        COLLECTOR_SUCCESS_NEW_DATA_TOTAL.labels(kind="competitor").inc()
        return "new_data", None
    
    #Agenda comparação mesmo quando não houve alteração para garantir difusão de preços atualizados
    compare_prices_task.apply_async(args=[str(monitored_id)], queue="monitor")
    COLLECTOR_SUCCESS_NO_CHANGE_TOTAL.labels(kind="competitor").inc()
    return "no_change", "not_modified"

def _record_outcome(
    *,
    kind: str,
    outcome: str,
    reason: str | None,
    task_logger,
    monitored_id: UUID | None,
    competitor_id: UUID | None,
) -> None:
    """ Atualiza métricas e logs para o desfecho informado, vinculando o produto """
    fields = {
        "kind": kind,
        "outcome": outcome,
        "product_id": str(competitor_id or monitored_id) if (competitor_id or monitored_id) else None,
        "monitored_id": str(monitored_id) if monitored_id else None,
        "competitor_id": str(competitor_id) if competitor_id else None,
    }
    if reason:
        fields["reason"] = reason
    task_logger.info("collect_product_outcome", **fields)


@shared_task(
    name="market_alert.tasks.collector_tasks.enqueue_due_monitored",
    bind=True,
    queue="monitor",
)
def enqueue_due_monitored(self) -> None:
    """ Task periódica que varre monitorados e enfileira coletas pendentes """
    with SessionLocal() as db:
        dispatched = schedule_due(db)
        logger.info("scheduled_monitored_rechecks", dispatched=dispatched)


def schedule_due(db: Session) -> int:
    """ Executa varredura de monitorados utilizando o serviço orquestrador """
    from market_alert.services.collector_services import schedule_due_monitored

    return schedule_due_monitored(db)


def _register_error(db: Session, product_id: UUID, url: str, message: str, error_type: ScrapingErrorType) -> None:
    """ Persiste erro de scraping com tolerância a falhas """
    try:
        crud_errors.create_scraping_error(db, product_id, url, message, error_type)
    except Exception:
        logger.warning("persist_scrape_error_failed", product_id=str(product_id))