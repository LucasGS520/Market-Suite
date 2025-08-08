""" Tarefas Celery relacionadas ao scraping de produtos.

Este módulo concentra as tasks responsáveis por coletar dados de produtos
monitorados e de concorrentes, utilizando apenas configurações locais e
um cliente HTTP dedicado para acionar o serviço ``market_scraper``. A
comunicação é feita via ``ScraperClient`` e o resultado é persistido no
banco de dados.
"""

from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal

import structlog

from infra.db import SessionLocal
from utils.redis_client import get_redis_client, is_scraping_suspended
from utils.scraper_client import ScraperClient, ScraperClientError

from alert_app.exceptions import ScraperError

from alert_app.core.config import settings
from alert_app.core.celery_app import celery_app

from alert_app.crud import crud_errors
from alert_app.crud.crud_monitored import create_or_update_monitored_product_scraped
from alert_app.crud.crud_competitor import create_or_update_competitor_product_scraped
from alert_app.schemas.schemas_products import MonitoredProductCreateScraping, MonitoredScrapedInfo, CompetitorProductCreateScraping, CompetitorScrapedInfo
from alert_app.tasks.compare_prices_tasks import compare_prices_task
from alert_app.enums.enums_error_codes import ScrapingErrorType
from alert_app.metrics import SCRAPING_LATENCY_SECONDS, SCRAPER_HEAD_FAILURES_TOTAL, SCRAPER_IN_FLIGHT


logger = structlog.get_logger("scraper_tasks")
redis_client = get_redis_client()
scraper_client = ScraperClient()

def _observe_metrics(start: datetime, task_name: str, status: str) -> None:
    """ Registra latência e contagem de tasks no Prometheus """
    duration = (datetime.now(timezone.utc) - start).total_seconds()
    SCRAPING_LATENCY_SECONDS.labels(source="scraper").observe(duration)

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

    # Execução do scraping propriamente dito e persistência dos dados
    product_id = monitored_id
    with SessionLocal() as db:
        try:
            #Envia requisição ao serviço externo de scraping
            details = scraper_client.parse(
                url=url,
                product_type="monitored",
            )

            #Persiste ou atualiza o produto monitorado com as informações obtidas
            product = create_or_update_monitored_product_scraped(
                db=db,
                user_id=UUID(user_id),
                product_data=payload,
                scraped_info=MonitoredScrapedInfo(
                    current_price=Decimal(str(details.get("current_price", 0))),
                    thumbnail=details.get("thumbnail"),
                    free_shipping=details.get("free_shipping", False),
                ),
                last_checked=datetime.now(timezone.utc),
            )
            product_id = str(product.id)
            compare_prices_task.delay(product_id)

            elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
            task_logger.info("collect_product_completed", duration_ms=elapsed_ms)
            redis_client.set("beat:last_success", datetime.now(timezone.utc).isoformat())
        except ScraperClientError as req_err:
            status = "failure"
            SCRAPER_HEAD_FAILURES_TOTAL.inc()
            task_logger.error("collect_product_http_error", error=str(req_err), monitored_product_id=product_id, url=url)
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
            status_code = req_err.status_code or 500
            raise ScraperError(status_code=status_code, detail=str(req_err))
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
            #Requisição ao serviço de scraping para coletar dados do concorrente
            details = scraper_client.parse(
                url=url,
                product_type="competitor",
            )

            #Persiste ou atualiza o concorrente com as informações obtidas
            create_or_update_competitor_product_scraped(
                db=db,
                product_data=payload,
                scraped_info=CompetitorScrapedInfo(
                    name=details.get("name", ""),
                    current_price=Decimal(str(details.get("current_price", 0))),
                    old_price=Decimal(str(details.get("old_price")))
                    if details.get("old_price") is not None
                    else None,
                    thumbnail=details.get("thumbnail"),
                    free_shipping=details.get("free_shipping", False),
                    seller=details.get("seller"),
                    seller_rating=None,
                ),
                last_checked=datetime.now(timezone.utc)
            )

            elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
            task_logger.info("collect_competitor_completed", duration_ms=elapsed_ms)

            compare_prices_task.delay(str(monitored_product_id))
            task_logger.info("price_comparison_task_dispatched")

        except ScraperClientError as req_err:
            status = "failure"
            SCRAPER_HEAD_FAILURES_TOTAL.inc()
            task_logger.error("collect_competitor_http_error", error=str(req_err), monitored_product_id=monitored_product_id, url=url)
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
            status_code = req_err.status_code or 500
            raise ScraperError(status_code=status_code, detail=str(req_err))

        except Exception as exc:
            status = "failure"
            task_logger.error("collect_competitor_failed", error=str(exc))

        finally:
            _observe_metrics(start, "collect_competitor_task", status)
            SCRAPER_IN_FLIGHT.dec()
