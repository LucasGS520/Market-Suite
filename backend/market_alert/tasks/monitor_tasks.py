""" Tarefas agendadas para monitoramento periódico.

As funções deste Módulo são executadas pelo Celery Beat e delegam as
coletas aos serviços ``scrape_monitored_product`` e ``scrape_competitor_product``,
para reaproveitar a política de retries, persistência de erros e métricas
padronizadas do pipeline.
"""

from datetime import datetime, timezone
import asyncio
import os
import time
from typing import Iterable, Sequence

import structlog

from shared.infra.db import SessionLocal
from shared.metrics.metrics_scraper import SCRAPING_LATENCY_SECONDS, SCRAPER_HEAD_FAILURES_TOTAL
from shared.utils.redis_client import  get_redis_client, is_scraping_suspended, suspend_scraping
from backend.shared.schemas.shared_schemas_products import (
    MonitoredProductCreateScraping,
    CompetitorProductCreateScraping,
)
from backend.shared.schemas.shared_schemas_scraper import ScrapeResult
from shared.enums.error_codes import ScrapingErrorType

from market_alert.core.config_alert import settings
from market_alert.core.celery_app import celery_app
from market_alert.enums.enums_products import MonitoringType
from market_alert.crud import crud_errors
from market_alert.crud.crud_monitored import (
    get_products_by_type,
    get_monitored_product_by_id,
    mark_monitored_product_failed,
)
from market_alert.crud.crud_competitor import get_all_competitor_products
from market_alert.tasks.compare_prices_tasks import compare_prices_task
from market_alert.scraper.scraper_client import ScraperClient, ScraperClientError
from market_alert.services.services_scraper_monitored import scrape_monitored_product
from market_alert.services.services_scraper_competitor import scrape_competitor_product


logger = structlog.get_logger("monitor_tasks")
redis_client = get_redis_client()
scraper_client = ScraperClient()

#Tamanho dos lotes para rechecagens de produtos e concorrentes
BATCH_SIZE_SCRAPING = int(os.getenv("BATCH_SIZE_SCRAPING", "10"))
BATCH_SIZE_COMPETITOR = int(os.getenv("BATCH_SIZE_COMPETITOR", "20"))

#TTL dos heartbeats em segundos (1 hora)
HEARTBEAT_TTL_SECONDS = 60 * 60


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

def _collect_batch_products(db, batch: Iterable, *, task, logger_bound) -> str:
    """ Processa lote de produtos monitorados retornando status agregado """
    status = "success"
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
            product_logger.error(
                "recheck_monitored_http_error",
                error=str(error),
                status_code=error.status_code,
                url=product.product_url,
            )
            _handle_http_error(task, db, product.id, product.product_url, error, logger_bound=product_logger)
            continue
        except Exception as exc:
            status = "failure"
            product_logger.error("recheck_monitored_unexpected_error", error=str(exc))
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
        
    return status

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
            competitor_logger.error(
                "recheck_competitor_http_error",
                error=str(error),
                status_code=error.status_code,
                url=competitor.product_url,
            )
            _handle_http_error(task, db, competitor.monitored_product_id, competitor.product_url, error, logger_bound=competitor_logger)
            continue

        except Exception as exc:
            status = "failure"
            competitor_logger.error("recheck_competitor_unexpected_error", error=str(exc))
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
        
        if result.price_changed:
            updated_ids.add(competitor.monitored_product_id)

    return status, updated_ids

async def _parse_monitored_batch(batch: Sequence) -> list:
    """ Executa parsing assíncrono de um lote de produtos monitorados """
    if not batch:
        #Retornamos lista vazia para manter compatibilidade com chamadores
        return []
    
    #Agrupamos as chamadas para rodarem em paralelo e reduzir a latência total
    coroutines = [
        scraper_client.parse(
            url=getattr(product, "product_url"),
            product_type="monitored",
            monitored_id=str(getattr(product, "id", "")),
            user_id=getattr(product, "user_id", None),
        )
        for product in batch
    ]
    return await asyncio.gather(*coroutines)

async def _parse_competitor_batch(batch: Sequence) -> list:
    """ Executa parsing assíncrono de um lote de produtos concorrentes """
    if not batch:
        return []
    
    coroutines = [
        scraper_client.parse(
            url=getattr(competitor, "product_url"),
            product_type="competitor",
            monitored_id=str(getattr(competitor, "monitored_product_id", "")),
            user_id=getattr(competitor, "user_id", None),
        )
        for competitor in batch
    ]
    return await asyncio.gather(*coroutines)

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

            status = _collect_batch_products(db, batch, task=self, logger_bound=task_logger)

            elapsed_ms = int((time.time() - started_at) * 1000)
            task_logger.info("recheck_monitored_completed", status=status, duration_ms=elapsed_ms, dispatched=len(batch))

            if redis_client is not None:
                redis_client.set("beat:last_scraping", datetime.now(timezone.utc).isoformat(), ex=HEARTBEAT_TTL_SECONDS)

    except self.MaxRetriesExceededError as exc:
        status = "failure"
        task_logger.error("recheck_monitored_max_retries", error=str(exc))
    except ScraperClientError as exc:
        #Erros não tratados em _collect_* sçao convertidos em log crítico
        status = "failure"
        task_logger.error("recheck_monitored_unhandled_http", error=str(exc), status_code=exc.status_code)
    except Exception as exc:
        status = "failure"
        task_logger.error("recheck_monitored_failed", error=str(exc))
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
        task_logger.error("recheck_competitors_max_retries", error=str(exc))
    except ScraperClientError as exc:
        status = "failure"
        task_logger.error("recheck_competitors_unhandled_http", error=str(exc), status_code=exc.status_code)
    except Exception as exc:
        status = "failure"
        task_logger.error("recheck_competitors_failed", error=str(exc))
        raise
    finally:
        _observe_latency("monitor_competitor", started_at)


__all__ = [
    "recheck_monitored_products",
    "recheck_competitor_products",
]
