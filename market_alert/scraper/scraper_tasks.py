""" Tarefas Celery relacionadas ao scraping de produtos.

Este módulo concentra as tasks responsáveis por coletar dados de produtos
monitorados e de concorrentes, delegando a coleta às funções de serviço
``scrape_monitored_product`` e ``scrape_competitor_product``. Essas
funções cuidam da comunicação com o serviço externo enquanto
as tasks mantêm métricas e tratamento de erros.
"""

from uuid import UUID
from datetime import datetime, timezone

import structlog

from shared.infra.db import SessionLocal
from shared.utils.redis_client import get_redis_client, is_scraping_suspended
from shared.exceptions import ScraperError
from shared.metrics.metrics_scraper import SCRAPING_LATENCY_SECONDS, SCRAPER_HEAD_FAILURES_TOTAL, SCRAPER_IN_FLIGHT
from shared.schemas.schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping
from shared.enums.error_codes import ScrapingErrorType

from market_alert.scraper.scraper_client import ScraperClientError

from market_alert.core.config_alert import settings
from market_alert.core.celery_app import celery_app
from market_alert.crud import crud_errors
from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.scraper.types import ScrapeResult
from market_alert.services.services_scraper_monitored import scrape_monitored_product
from market_alert.services.services_scraper_competitor import scrape_competitor_product
from market_alert.tasks.compare_prices_tasks import compare_prices_task


logger = structlog.get_logger("scraper_tasks")
redis_client = get_redis_client()

def _observe_metrics(start: datetime, task_name: str, status: str) -> None:
    """ Registra latência e contagem de tasks no Prometheus """
    duration = (datetime.now(timezone.utc) - start).total_seconds()
    SCRAPING_LATENCY_SECONDS.labels(source="scraper").observe(duration)

def _compute_retry_delay(base: float, attempt: int, limit: int) -> int:
    """ Calcula atraso exponencial limitado para retries no Celery """
    delay = base * (2 ** max(0, attempt - 1))
    return min(int(delay), limit)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=30, name="collect_product_task", rate_limit=settings.SCRAPER_RATE_LIMIT, queue="scraping")
def collect_product_task(self, url: str, user_id: str, name_identification: str, target_price: float, monitored_id: str | None = None) -> None:
    """ Coleta dados de um produto monitorado e os salva no banco """
    SCRAPER_IN_FLIGHT.inc()
    task_logger = logger.bind(task_id=self.request.id, url=url, user_id=user_id)

    start = datetime.now(timezone.utc)
    status = "success"
    task_logger.info("collect_product_started")

    #Checa flag de suspensão global
    if is_scraping_suspended():
        status = "failure"
        task_logger.warning("suspended_via_flag", detail="scraping suspended flag is set")
        _observe_metrics(start, "collect_product_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return

    #Validação e preparação do payload recebido
    try:
        payload = MonitoredProductCreateScraping.model_validate(
            {
                "name_identification": name_identification,
                "product_url": url,
                "target_price": target_price
            }
        )
    except Exception as exc:
        status = "failure"
        task_logger.error("invalid_payload", error=str(exc))
        _observe_metrics(start, "collect_product_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return

    #Execução do scraping delegada ao serviço especializado
    product_id = monitored_id
    with SessionLocal() as db:
        try:
            result: ScrapeResult = scrape_monitored_product(
                db=db,
                url=url,
                user_id=UUID(user_id),
                payload=payload,
            )
            product_id = result.product_id

            if result.status == "no_result":
                status = "failure"
                task_logger.warning("collect_product_no_result")
                if result.product_id:
                    crud_errors.create_scraping_error(
                        db,
                        UUID(result.product_id),
                        url,
                        "pipeline retornou no_result",
                        ScrapingErrorType.no_result,
                    )
                retry_delay = min(
                    settings.SCRAPER_NO_RESULT_RETRY_SECONDS * (self.request.retries + 1),
                    settings.SCRAPER_MAX_RETRY_DELAY_SECONDS,
                )
                raise self.retry(countdown=retry_delay)

            elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
            task_logger.info(
                "collect_product_completed",
                duration_ms=elapsed_ms,
                status=result.status,
                price_changed=result.price_changed,
            )
            if redis_client is not None:
                redis_client.set("beat:last_success", datetime.now(timezone.utc).isoformat())
        except ScraperClientError as req_err:
            status = "failure"
            SCRAPER_HEAD_FAILURES_TOTAL.inc()
            task_logger.error(
                "collect_product_http_error",
                error=str(req_err),
                monitored_product_id=product_id,
                url=url,
                status_code=req_err.status_code,
            )
            if product_id:
                try:
                    crud_errors.create_scraping_error(
                        db,
                        UUID(product_id),
                        url,
                        str(req_err),
                        ScrapingErrorType.http_error,
                    )
                except Exception as err:
                    task_logger.warning("error_persist_failed", error=str(err))
            
            if req_err.status_code and 500 <= req_err.status_code < 600:
                delay = _compute_retry_delay(
                    settings.SCRAPER_RETRY_BACKOFF_MIN,
                    self.request.retries + 1,
                    settings.SCRAPER_MAX_RETRY_DELAY_SECONDS,
                )
                raise self.retry(countdown=delay)
            
            if req_err.status_code == 429 and req_err.retry_after:
                raise self.retry(countdown=req_err.retry_after)
            
            raise ScraperError(status_code=req_err.status_code or 500, detail=str(req_err))
        except self.MaxRetriesExceededError as exc:
            status = "failure"
            task_logger.error("max_retries_exceeded", error=str(exc))
        except Exception as exc:
            status = "failure"
            task_logger.error("collect_product_failed", error=str(exc))
            if product_id:
                try:
                    crud_errors.create_scraping_error(
                        db,
                        UUID(product_id),
                        url,
                        str(exc),
                        ScrapingErrorType.parsing_error,
                    )
                except Exception as err:
                    task_logger.warning("error_persist_failed", error=str(err))
        finally:
            _observe_metrics(start, "collect_product_task", status)
            SCRAPER_IN_FLIGHT.dec()

@celery_app.task(bind=True, max_retries=3, default_retry_delay=30, name="collect_competitor_task", rate_limit=settings.COMPETITOR_RATE_LIMIT, queue="scraping")
def collect_competitor_task(self, monitored_product_id: str, url: str) -> None:
    """ Coleta dados de um produto concorrente e compara os preços. """
    SCRAPER_IN_FLIGHT.inc()
    task_logger = logger.bind(task_id=self.request.id, monitored_product_id=monitored_product_id, url=url)

    start = datetime.now(timezone.utc)
    status = "success"
    task_logger.info("collect_competitor_started")

    #Checa flag de suspensão global
    if is_scraping_suspended():
        task_logger.warning("suspended_via_flag", detail="scraping suspended flag is set")
        status = "failure"
        _observe_metrics(start, "collect_competitor_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return

    #Preparação payload
    try:
        payload = CompetitorProductCreateScraping.model_validate({
            "monitored_product_id": monitored_product_id,
            "product_url": url
        })
    except Exception as exc:
        status = "failure"
        task_logger.error("invalid_payload", error=str(exc))
        _observe_metrics(start, "collect_competitor_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return

    #Scraping propriamente dito e agendamento de comparação de preços
    with SessionLocal() as db:
        try:
            monitored = get_monitored_product_by_id(db, UUID(monitored_product_id))
            user_id = monitored.user_id if monitored else UUID(int=0)

            result: ScrapeResult = scrape_competitor_product(
                db=db,
                user_id=user_id,
                url=url,
                payload=payload,
            )

            elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
            task_logger.info(
                "collect_competitor_completed", 
                duration_ms=elapsed_ms,
                status=result.status,
                price_changed=result.price_changed,
            )

            if result.status == "no_result":
                status = "failure"
                crud_errors.create_scraping_error(
                    db,
                    UUID(monitored_product_id),
                    url,
                    "pipeline retornou no_result",
                    ScrapingErrorType.no_result,
                )
                delay = min(
                    settings.SCRAPER_NO_RESULT_RETRY_SECONDS * (self.request.retries + 1),
                    settings.SCRAPER_MAX_RETRY_DELAY_SECONDS,
                )
                raise self.retry(countdown=delay)
            
            if result.price_changed:
                compare_prices_task.delay(str(monitored_product_id))
                task_logger.info("price_comparison_task_dispatched")

        except ScraperClientError as req_err:
            status = "failure"
            SCRAPER_HEAD_FAILURES_TOTAL.inc()
            task_logger.error(
                "collect_competitor_http_error",
                error=str(req_err),
                monitored_product_id=monitored_product_id,
                url=url,
                status_code=req_err.status_code,
            )
            try:
                crud_errors.create_scraping_error(
                    db,
                    UUID(monitored_product_id),
                    url,
                    str(req_err),
                    ScrapingErrorType.http_error,
                )
            except Exception as err:
                task_logger.warning("error_persist_failed", error=str(err))
            
            if req_err.status_code and 500 <= req_err.status_code < 600:
                delay = _compute_retry_delay(
                    settings.SCRAPER_RETRY_BACKOFF_MIN,
                    self.request.retries + 1,
                    settings.SCRAPER_MAX_RETRY_DELAY_SECONDS,
                )
                raise self.retry(countdown=delay)
            
            if req_err.status_code == 429 and req_err.retry_after:
                raise self.retry(countdown=req_err.retry_after)
            
            raise ScraperError(status_code=req_err.status_code or 500, detail=str(req_err))
        
        except self.MaxRetriesExceededError as exc:
            status = "failure"
            task_logger.error("max_retries_exceeded", error=str(exc))

        except Exception as exc:
            status = "failure"
            task_logger.error("collect_competitor_failed", error=str(exc))

        finally:
            _observe_metrics(start, "collect_competitor_task", status)
            SCRAPER_IN_FLIGHT.dec()
