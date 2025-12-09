""" Tarefas agendadas para monitoramento periódico.

As funções deste Módulo são executadas pelo Celery Beat e delegam as
coletas aos serviços ``scrape_monitored_product`` e ``scrape_competitor_product``,
para reaproveitar a política de retries, persistência de erros e métricas
padronizadas do pipeline.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
import time
from typing import Iterable
from uuid import UUID

import structlog
from celery.exceptions import SoftTimeLimitExceeded

from shared.infra.db import SessionLocal
from shared.metrics.metrics_scraper import (
    RECHECK_COMPETITOR_RESULT_TOTAL,
    RECHECK_MONITORED_RESULT_TOTAL,
    SCRAPING_LATENCY_SECONDS,
    SCRAPER_HEAD_FAILURES_TOTAL,
)
from shared.utils.redis_client import get_redis_client, is_scraping_suspended, suspend_scraping
from shared.exceptions import ScraperError
from backend.shared.schemas.shared_schemas_products import (
    MonitoredProductCreateScraping,
    CompetitorProductCreateScraping,
)
from backend.shared.schemas.shared_schemas_scraper import ScrapeResult
from shared.enums.error_codes import ScrapingErrorType

from market_alert.core.config_alert import settings
from market_alert.core.celery_app import celery_app
from market_alert.enums.enums_products import MonitoringType, MonitoredStatus
from market_alert.crud import crud_errors
from market_alert.crud.crud_monitored import (
    get_products_by_type,
    get_monitored_product_by_id,
    mark_monitored_product_failed,
)
from market_alert.crud.crud_competitor import get_all_competitor_products, get_competitors_by_monitored_id
from market_alert.tasks.compare_prices_tasks import compare_prices_task
from market_alert.scraper.scraper_client import ScraperClientError
from market_alert.services.services_scraper_monitored import scrape_monitored_product
from market_alert.services.services_scraper_competitor import scrape_competitor_product
from market_alert.services.services_comparison import run_price_comparison
from market_alert.models.models_products import MonitoredProduct


logger = structlog.get_logger("monitor_tasks")
redis_client = get_redis_client()

#Tamanho dos lotes para rechecagens de produtos e concorrentes
BATCH_SIZE_SCRAPING = int(os.getenv("BATCH_SIZE_SCRAPING", "10"))
BATCH_SIZE_COMPETITOR = int(os.getenv("BATCH_SIZE_COMPETITOR", "20"))

#TTL dos heartbeats em segundos (1 hora)
HEARTBEAT_TTL_SECONDS = 60 * 60

@dataclass
class CollectionOutcome:
    """ Representa o desfecho padronizado de uma coleta sincronizada """
    status: str
    reason: str | None = None
    product_id: UUID | None = None
    price_changed: bool = False
    availability_changed: bool = False

    @property
    def has_data(self) -> bool:
        """ Indica se a coleta retornou dados válidos para uso """
        return self.status.startswith("success")

def _compute_next_check_at(monitored: MonitoredProduct, reference: datetime) -> datetime:
    """ Calcula o próximo agendamento de rechecagem respeitando configuração dinâmica """
    interval_seconds = getattr(monitored, "check_interval", None)
    if not isinstance(interval_seconds, int) or interval_seconds <= 0:
        interval_seconds = settings.RECHECK_INTERVAL_DEFAULT
    return reference + timedelta(seconds=interval_seconds)

def _mark_recheck_started(db: SessionLocal, monitored_id: UUID, started_at: datetime, *, logger_bound) -> bool:
    """ Marca o monitorado como em rechecagem de forma atômica """
    updated = (
        db.query(MonitoredProduct)
        .filter(
            MonitoredProduct.id == monitored_id,
            MonitoredProduct.checking_in_progress.is_(False),
        )
        .update(
            {"checking_in_progress": True, "checking_started_at": started_at},
            synchronize_session=False,
        )
    )
    if not updated:
        db.rollback()
        return False
    db.commit()
    logger_bound.info("recheck_started", monitored_id=str(monitored_id), started_at=started_at.isoformat())
    return True

def _finalize_recheck_state(
    db: SessionLocal,
    monitored_id: UUID,
    *,
    last_checked: datetime | None,
    next_check_at: datetime,
) -> None:
    """ Atualiza timestamps e libera a flag de progresso com tolerância a falhas """
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

def _collect_monitored_single(db: SessionLocal, monitored: MonitoredProduct, *, logger_bound) -> CollectionOutcome:
    """ Executa coleta do monitorado e normaliza status para o orquestrador """
    payload = MonitoredProductCreateScraping(
        name_identification=monitored.name_identification,
        product_url=monitored.product_url,
    )

    try:
        result: ScrapeResult = scrape_monitored_product(
            db=db,
            url=monitored.product_url,
            user_id=monitored.user_id,
            payload=payload,
        )
    except ScraperError as exc:
        logger_bound.warning("monitored_collect_error", error=str(exc))
        return CollectionOutcome(status="error", reason="scraper_error", product_id=monitored.id)
    except Exception as exc:
        logger_bound.exception("monitored_collect_unexpected")
        return CollectionOutcome(status="error", reason="unexpected", product_id=monitored.id)

    if result.status == "no_result":
        return CollectionOutcome(status="no_data", reason="no_result", product_id=monitored.id)

    if result.status == "not_modified":
        return CollectionOutcome(status="success_no_change", reason="not_modified", product_id=monitored.id)

    if result.status != "success":
        return CollectionOutcome(status="error", reason=result.status, product_id=monitored.id)

    changed = bool(getattr(result, "price_changed", False) or getattr(result, "availability_changed", False))
    status = "success_new" if changed else "success_no_change"
    return CollectionOutcome(
        status=status,
        reason=None,
        product_id=monitored.id,
        price_changed=getattr(result, "price_changed", False),
        availability_changed=getattr(result, "availability_changed", False),
    )

def _collect_competitor_single(db: SessionLocal, competitor, user_id: UUID, *, logger_bound) -> CollectionOutcome:
    """ Executa coleta de um concorrente de forma isolada e robusta """
    payload = CompetitorProductCreateScraping(
        monitored_product_id=competitor.monitored_product_id,
        product_url=competitor.product_url,
    )

    try:
        result: ScrapeResult = scrape_competitor_product(
            db=db,
            user_id=user_id,
            url=competitor.product_url,
            payload=payload,
        )
    except ScraperError as exc:
        logger_bound.warning("competitor_collect_error", error=str(exc))
        return CollectionOutcome(status="error", reason="scraper_error", product_id=competitor.id)
    except Exception:
        logger_bound.exception("competitor_collect_unexpected")
        return CollectionOutcome(status="error", reason="unexpected", product_id=competitor.id)

    if result.status == "no_result":
        return CollectionOutcome(status="no_data", reason="no_result", product_id=competitor.id)

    if result.status == "not_modified":
        return CollectionOutcome(status="success_no_change", reason="not_modified", product_id=competitor.id)

    if result.status != "success":
        return CollectionOutcome(status="error", reason=result.status, product_id=competitor.id)

    changed = bool(getattr(result, "price_changed", False) or getattr(result, "availability_changed", False))
    status = "success_new" if changed else "success_no_change"
    return CollectionOutcome(
        status=status,
        reason=None,
        product_id=competitor.id,
        price_changed=getattr(result, "price_changed", False),
        availability_changed=getattr(result, "availability_changed", False),
    )

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

    try:
        monitored_uuid = UUID(str(monitored_id))
    except Exception:
        task_logger.error("invalid_monitored_identifier")
        return

    with SessionLocal() as db:
        monitored = get_monitored_product_by_id(db, monitored_uuid)
        if monitored is None or monitored.status == MonitoredStatus.failed:
            task_logger.info("recheck_skipped_missing", status=str(getattr(monitored, "status", "missing")))
            return

        if not _mark_recheck_started(db, monitored.id, started_at, logger_bound=task_logger):
            task_logger.info("recheck_already_running")
            return

        next_check_at = _compute_next_check_at(monitored, started_at)
        previous_last_checked = monitored.last_checked

        try:
            monitor_outcome = _collect_monitored_single(db, monitored, logger_bound=task_logger)
            RECHECK_MONITORED_RESULT_TOTAL.labels(result=monitor_outcome.status).inc()
            task_logger.info(
                "monitor_collect_result",
                status=monitor_outcome.status,
                reason=monitor_outcome.reason,
            )

            if monitor_outcome.status in {"error", "no_data"}:
                _finalize_recheck_state(
                    db,
                    monitored.id,
                    last_checked=previous_last_checked,
                    next_check_at=next_check_at,
                )
                task_logger.warning("recheck_aborted", reason=monitor_outcome.reason)
                return

            competitors = get_competitors_by_monitored_id(db, monitored.id)
            for competitor in competitors:
                outcome = _collect_competitor_single(
                    db, competitor, monitored.user_id, logger_bound=task_logger.bind(competitor_id=str(competitor.id))
                )
                RECHECK_COMPETITOR_RESULT_TOTAL.labels(result=outcome.status).inc()
                task_logger.info(
                    "competitor_collect_result",
                    status=outcome.status,
                    reason=outcome.reason,
                    competitor_id=str(competitor.id),
                )

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
            )
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
        except Exception:
            _finalize_recheck_state(
                db,
                monitored.id,
                last_checked=previous_last_checked,
                next_check_at=next_check_at,
            )
            task_logger.exception("recheck_failed")
            raise

def _compute_retry_delay(base: float, attempt: int, limit: int) -> int:
    """ Calcula um atraso exponencial limitado para reagendamentos automáticos """
    delay = base * (2 ** max(0, attempt - 1))
    return min(int(delay), limit)

def _compute_no_result_delay(attempt: int) -> int:
    """ Ajusta o intervalo de retry quando o scraper retorna ``no_result`` """
    delay = settings.SCRAPER_NO_RESULT_RETRY_SECONDS * attempt
    return min(delay, settings.SCRAPER_MAX_RETRY_DELAY_SECONDS)

def _mark_monitored_failed(db, product_id, *, logger_bound) -> None:
    """ Atualiza status do produto para ``failed`` registrando timestamp atual """
    if not hasattr(db, "query"):
        logger_bound.info("mark_failed_skipped", reason="session_without_query")
        return
    
    try:
        mark_monitored_product_failed(db, product_id, touched_at=datetime.now(timezone.utc))
        logger_bound.info("monitored_marked_failed", monitored_id=str(product_id))
    except Exception as exc:
        logger_bound.warning("mark_failed_persist_error", monitored_id=str(product_id), error=str(exc))

def _persist_scraping_error(db, product_id, url: str, message: str, error_type: ScrapingErrorType, *, logger_bound) -> None:
    """ Guarda o erro de scraping com tolerância a falhas de persistência """
    try:
        crud_errors.create_scraping_error(db, product_id, url, message, error_type)
    except Exception as persist_err:
        logger_bound.warning("error_persist_failed", error=str(persist_err))

def _handle_http_error(task, db, product_id, url: str, error: ScraperClientError, *, logger_bound) -> None:
    """ Normaliza tratamento de ``ScraperClientError`` aplicando métricas e retries """
    SCRAPER_HEAD_FAILURES_TOTAL.inc()
    _persist_scraping_error(db, product_id, url, str(error), ScrapingErrorType.http_error, logger_bound=logger_bound)

    status_code = error.status_code or 0
    attempt = task.request.retries + 1
    max_retries = getattr(task, "max_retries", None) or 0

    #Se o scraper sinaliza retry-after, usamos o mesmo intervalo e suspendemos coletas
    if status_code == 429:
        countdown = error.retry_after or _compute_retry_delay(settings.SCRAPER_RETRY_BACKOFF_MIN, attempt, settings.SCRAPER_MAX_RETRY_DELAY_SECONDS)
        if max_retries and attempt >= max_retries:
            logger_bound.warning("scraping_retry_exhausted", status_code=status_code, url=url)
            return
        if countdown > 0:
            suspend_scraping(countdown)
        raise task.retry(countdown=countdown)
    
    #Falhas 5xx merecem retry exponencial
    if 500 <= status_code < 600:
        countdown = _compute_retry_delay(settings.SCRAPER_RETRY_BACKOFF_MIN, attempt, settings.SCRAPER_MAX_RETRY_DELAY_SECONDS)
        if max_retries and attempt >= max_retries:
            logger_bound.warning("scraping_retry_exhausted", status_code=status_code, url=url)
            _mark_monitored_failed(db, product_id, logger_bound=logger_bound)
            return
        raise task.retry(countdown=countdown)
    
    #Bloqueios explícitos por robots exigem apenas log para diagnóstico
    if status_code in {403, 451}:
        logger_bound.warning("scraping_blocked_by_robots", status_code=status_code, url=url)
        _mark_monitored_failed(db, product_id, logger_bound=logger_bound)
        return
    
    #Demais erros 4xx não possuem ação automática além de log estruturado
    logger_bound.error("scraping_http_error", status_code=status_code, url=url)
    _mark_monitored_failed(db, product_id, logger_bound=logger_bound)

def _build_monitored_paylaod(product) -> MonitoredProductCreateScraping:
    """ Constrói o payload compatível com o serviço de monitorados """
    return MonitoredProductCreateScraping(
        name_identification=product.name_identification,
        product_url=product.product_url,
    )

def _build_competitor_payload(competitor) -> CompetitorProductCreateScraping:
    """ Constrói o payload compatível com o serviço de concorrentes """
    return CompetitorProductCreateScraping(
        monitored_product_id=competitor.monitored_product_id,
        product_url=competitor.product_url,
    )

def _observe_latency(source: str, started_at: float) -> None:
    """ Consolida a latência da task para Prometheus """
    duration = time.time() - started_at
    SCRAPING_LATENCY_SECONDS.labels(source=source).observe(duration)

def _collect_batch_products(db, batch: Iterable, *, task, logger_bound) -> tuple[str, set]:
    """ Processa lote de produtos monitorados retornando status agregado """
    status = "success"
    updated_ids: set[str] = set()
    for product in batch:
        product_logger = logger_bound.bind(monitored_id=str(product.id))
        payload = _build_monitored_paylaod(product)
    
        try:
            result: ScrapeResult = scrape_monitored_product(
                db=db,
                url=product.product_url,
                user_id=product.user_id,
                payload=payload,
            )
        except ScraperClientError as error:
            status = "failure"
            product_logger.exception(
                "recheck_monitored_http_error",
                status_code=error.status_code,
                url=product.product_url,
            )
            _handle_http_error(task, db, product.id, product.product_url, error, logger_bound=product_logger)
            continue
        except Exception as exc:
            status = "failure"
            product_logger.exception("recheck_monitored_unexpected_error")
            _persist_scraping_error(db, product.id, product.product_url, str(exc), ScrapingErrorType.parsing_error, logger_bound=product_logger)
            _mark_monitored_failed(db, product.id, logger_bound=product_logger)
            continue

        if result.status == "no_result":
            status = "failure"
            product_logger.warning("recheck_monitored_no_result")
            _persist_scraping_error(
                db,
                product.id,
                product.product_url,
                "pipeline retornou no_result",
                ScrapingErrorType.no_result,
                logger_bound=product_logger,
            )
            attempt = task.request.retries + 1
            max_retries = getattr(task, "max_retries", None) or 0
            if max_retries and attempt >= max_retries:
                _mark_monitored_failed(db, product.id, logger_bound=product_logger)
                continue
            countdown = _compute_no_result_delay(attempt)
            raise task.retry(countdown=countdown)
        
        if getattr(result, "price_changed", False) or getattr(result, "availability_changed", False):
            updated_ids.add(str(product.id))

    return status, updated_ids

def _collect_batch_competitors(db, batch: Iterable, *, task, logger_bound) -> tuple[str, set]:
    """ Processa lote de concorrentes retornando status agregado e IDs atualizados """
    status = "success"
    updated_ids: set = set()

    for competitor in batch:
        competitor_logger = logger_bound.bind(competitor_id=str(competitor.id))
        payload = _build_competitor_payload(competitor)

        try:
            monitored = getattr(competitor, "monitored_product", None)
            if monitored is None:
                monitored = get_monitored_product_by_id(db, competitor.monitored_product_id)

            user_id = monitored.user_id if monitored is not None else competitor.monitored_product_id

            result: ScrapeResult = scrape_competitor_product(
                db=db,
                user_id=user_id,
                url=competitor.product_url,
                payload=payload,
            )
        except ScraperClientError as error:
            status = "failure"
            competitor_logger.exception(
                "recheck_competitor_http_error",
                status_code=error.status_code,
                url=competitor.product_url,
            )
            _handle_http_error(task, db, competitor.monitored_product_id, competitor.product_url, error, logger_bound=competitor_logger)
            continue

        except Exception as exc:
            status = "failure"
            competitor_logger.exception("recheck_competitor_unexpected_error")
            _persist_scraping_error(
                db,
                competitor.monitored_product_id,
                competitor.product_url,
                str(exc),
                ScrapingErrorType.parsing_error,
                logger_bound=competitor_logger,
            )
            continue

        if result.status == "no_result":
            status = "failure"
            competitor_logger.warning("recheck_competitor_no_result")
            _persist_scraping_error(
                db,
                competitor.monitored_product_id,
                competitor.product_url,
                "pipeline retornou no_result",
                ScrapingErrorType.no_result,
                logger_bound=competitor_logger,
            )
            countdown = _compute_no_result_delay(task.request.retries + 1)
            raise task.retry(countdown=countdown)
        
        if getattr(result, "price_changed", False) or getattr(result, "availability_changed", False):
            updated_ids.add(competitor.monitored_product_id)

    return status, updated_ids

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="market_alert.tasks.monitor_tasks.recheck_monitored_products",
)
def recheck_monitored_products(self) -> None:
    """ Rechecagem periódica de produtos monitorados via scraping """
    started_at = time.time()
    status = "success"
    task_logger = logger.bind(task_id=getattr(self.request, "id", None), phase="recheck_scraping")

    try:
        #Flag de suspensão global controlada via Redis
        if is_scraping_suspended():
            status = "failure"
            task_logger.warning("suspended_via_flag", detail="scraping suspended flag is set")
            return
        
        with SessionLocal() as db:
            products = get_products_by_type(db, MonitoringType.scraping)
            batch = products[:BATCH_SIZE_SCRAPING]

            status, updated_ids = _collect_batch_products(db, batch, task=self, logger_bound=task_logger)

            for monitored_id in updated_ids:
                compare_prices_task.delay(str(monitored_id))

            elapsed_ms = int((time.time() - started_at) * 1000)
            task_logger.info("recheck_monitored_completed", status=status, duration_ms=elapsed_ms, dispatched=len(batch))

            if redis_client is not None:
                redis_client.set("beat:last_scraping", datetime.now(timezone.utc).isoformat(), ex=HEARTBEAT_TTL_SECONDS)

    except self.MaxRetriesExceededError as exc:
        status = "failure"
        task_logger.exception("recheck_monitored_max_retries")
    except ScraperClientError as exc:
        #Erros não tratados em _collect_* sçao convertidos em log crítico
        status = "failure"
        task_logger.exception("recheck_monitored_unhandled_http", status_code=exc.status_code)
    except Exception as exc:
        status = "failure"
        task_logger.exception("recheck_monitored_failed")
        raise
    finally:
        _observe_latency("monitor_scraper", started_at)

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="market_alert.tasks.monitor_tasks.recheck_competitor_products",
)
def recheck_competitor_products(self) -> None:
    """ Rechecagem periódica de produtos concorrentes e comparação de preços """
    started_at = time.time()
    status = "success"
    task_logger = logger.bind(task_id=getattr(self.request, "id", None), phase="recheck_competitors")

    try:
        if is_scraping_suspended():
            status = "failure"
            task_logger.warning("suspended_via_flag", detail="scraping suspended flag is set")
            return
        
        with SessionLocal() as db:
            competitors = get_all_competitor_products(db)
            batch = competitors[:BATCH_SIZE_COMPETITOR]

            status, updated_ids = _collect_batch_competitors(db, batch, task=self, logger_bound=task_logger)

            for monitored_id in updated_ids:
                #Disparamos comparação apenas para monitorados com preço alterado
                compare_prices_task.delay(str(monitored_id))

            elapsed_ms = int((time.time() - started_at) * 1000)
            task_logger.info("recheck_competitors_completed", status=status, duration_ms=elapsed_ms, count=len(batch))

            if redis_client is not None:
                redis_client.set("beat:last_competitor", datetime.now(timezone.utc).isoformat(), ex=HEARTBEAT_TTL_SECONDS)

    except self.MaxRetriesExceededError as exc:
        status = "failure"
        task_logger.exception("recheck_competitors_max_retries")
    except ScraperClientError as exc:
        status = "failure"
        task_logger.exception("recheck_competitors_unhandled_http", status_code=exc.status_code)
    except Exception as exc:
        status = "failure"
        task_logger.exception("recheck_competitors_failed")
        raise
    finally:
        _observe_latency("monitor_competitor", started_at)


__all__ = [
    "recheck_monitored_product",
    "recheck_monitored_products",
    "recheck_competitor_products",
]
