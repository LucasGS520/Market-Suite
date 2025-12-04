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
from shared.metrics.metrics_scraper import SCRAPER_IN_FLIGHT
from shared.utils.redis_client import is_scraping_suspended
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


logger = structlog.get_logger("collect_task")

class _RetryableError(Exception):
    """ Erro interno para sinalizar retries controlados """

@celery_app.task(
    bind=True,
    max_retries=settings.SCRAPER_RETRY_ATTEMPTS,
    default_retry_delay=settings.SCRAPER_RETRY_BACKOFF_MIN,
    name="market_alert.tasks.collect_task.collect_product_task",
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
    try:
        if target_kind == "competitor":
            _process_competitor(task_logger, payload)
        else:
            _process_monitored(task_logger, payload)
    except _RetryableError as exc:
        SCRAPER_IN_FLIGHT.dec()
        raise self.retry(exc=exc)
    except Exception:
        task_logger.exception("collect_product_failed", kind=target_kind)
    finally:
        SCRAPER_IN_FLIGHT.dec()
        elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        task_logger.info("collect_product_finished", kind=target_kind, duration_ms=elapsed_ms)


def _process_monitored(task_logger, payload: Mapping[str, str]) -> None:
    """ Executa coleta de monitorado e enfileira concorrentes associados """
    if is_scraping_suspended():
        task_logger.warning("scraping_suspended")
        return

    try:
        monitored_id = UUID(str(payload["monitored_id"]))
        user_id = UUID(str(payload["user_id"]))
    except Exception as exc:
        task_logger.error("invalid_monitored_reference", error=str(exc))
        return

    product_url = payload.get("url")
    name_identification = payload.get("name")

    parsed_limit = parse_rate_limit_config(settings.SCRAPER_RATE_LIMIT)
    if parsed_limit:
        bucket_key = f"rate:scrape:{user_id}"
        if not allow_with_leaky_bucket(bucket_key, rate_limit=parsed_limit):
            task_logger.warning("monitored_rate_limit", monitored_id=str(monitored_id))
            return

    payload_model = MonitoredProductCreateScraping(
        product_url=product_url,
        name_identification=name_identification,
    )

    with SessionLocal() as db:
        _run_monitored_scrape(db, task_logger, monitored_id, user_id, payload_model)


def _run_monitored_scrape(
    db: Session,
    task_logger,
    monitored_id: UUID,
    user_id: UUID,
    payload: MonitoredProductCreateScraping,
) -> None:
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
        return
    except Exception as exc:
        task_logger.exception("unexpected_monitored_error")
        _register_error(db, monitored_id, str(payload.product_url), str(exc), ScrapingErrorType.parsing_error)
        return

    if result.status == "no_result":
        raise _RetryableError("monitored_no_result")

    if getattr(result, "price_changed", False) or getattr(result, "availability_changed", False):
        compare_prices_task.delay(str(monitored_id))

    enqueue_competitors_for_monitored(db, monitored_id)


def _process_competitor(task_logger, payload: Mapping[str, str]) -> None:
    """ Executa coleta de concorrente e dispara comparação do monitorado """
    if is_scraping_suspended():
        task_logger.warning("scraping_suspended")
        return

    try:
        monitored_id = UUID(str(payload["monitored_id"]))
    except Exception as exc:
        task_logger.error("invalid_monitored_reference", error=str(exc))
        return

    user_id = payload.get("user_id")
    user_uuid = UUID(str(user_id)) if user_id else None
    product_url = payload.get("url")

    payload_model = CompetitorProductCreateScraping(
        monitored_product_id=monitored_id,
        product_url=product_url,
    )

    with SessionLocal() as db:
        _run_competitor_scrape(db, task_logger, monitored_id, user_uuid, payload_model)


def _run_competitor_scrape(
    db: Session,
    task_logger,
    monitored_id: UUID,
    user_id: UUID | None,
    payload: CompetitorProductCreateScraping,
) -> None:
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
        return
    except Exception as exc:
        task_logger.exception("unexpected_competitor_error")
        _register_error(db, monitored_id, str(payload.product_url), str(exc), ScrapingErrorType.parsing_error)
        return

    if result.status == "no_result":
        raise _RetryableError("competitor_no_result")

    if getattr(result, "price_changed", False) or getattr(result, "availability_changed", False):
        compare_prices_task.delay(str(monitored_id))


@shared_task(
    name="market_alert.tasks.collect_task.enqueue_due_monitored",
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