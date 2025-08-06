""" Tarefas Celery relacionadas a scraping de produtos.

Este módulo contém tasks que fazem o scraping de produtos monitorados e de
concorrentes. Cada task aplica mecanismos de *rate limiting* e *circuit
breaker* para evitar bloquear o acesso ao site alvo e registrar métricas de
desempenho. O parâmetro ``rate_limit`` definido no decorador das tasks
controla quantas vezes cada worker pode iniciar essas tarefas em determinado
período independente do agendamento adaptativo que define quando cada
produto será verificado novamente
"""

from uuid import UUID
from datetime import datetime, timezone

import structlog
from fastapi import HTTPException

from app.exceptions import ScraperError

from app.core.config import settings
from app.core.celery_app import celery_app
from infra.db import SessionLocal
from utils.redis_client import get_redis_client, is_scraping_suspended
from utils.circuit_breaker import CircuitBreaker
from utils.rate_limiter import RateLimiter
from app.utils.adaptive_recheck import AdaptiveRecheckManager
from app.crud.crud_monitored import get_monitored_product_by_id
from app.crud.crud_comparison import get_latest_comparisons
from market_scraper.app.core.config import settings as scraper_settings #COnfigurações do módulo de scraping

from app.schemas.schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping

from app.services.services_scraper_monitored import scrape_monitored_product
from app.services.services_scraper_competitor import scrape_competitor_product
from app.tasks.compare_prices_tasks import compare_prices_task
from app.crud import crud_errors
from app.enums.enums_error_codes import ScrapingErrorType
from app.metrics import SCRAPING_LATENCY_SECONDS, SCRAPER_HEAD_FAILURES_TOTAL, SCRAPER_IN_FLIGHT


logger = structlog.get_logger("scraper_tasks")
redis_client = get_redis_client()

circuit_breaker = CircuitBreaker()
#Intervalo base definido nas configurações do scraper
adaptive_recheck = AdaptiveRecheckManager(
    base_interval=scraper_settings.ADAPTIVE_RECHECK_BASE_INTERVAL
)

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
    adaptive_recheck.redis = redis_client

    # Checa flag de suspensão global
    if is_scraping_suspended():
        status = "failure"
        task_logger.warning("suspended_via_flag", detail="scraping suspended flag is set")
        _observe_metrics(start, "collect_product_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return

    # Circuit breaker evita novas requisições em caso de falhas consecutivas
    if not circuit_breaker.allow_request("collect_product_task"):
        status = "failure"
        task_logger.error("circuit_open", detail="circuit breaker open")
        _observe_metrics(start, "collect_product_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return

    # Rate limiter específico desta task
    monitored_rate_limiter = RateLimiter(
        redis_key="rate:collect_product_task",
        max_requests=5,
        window_seconds=60
    )

    if not monitored_rate_limiter.allow_request():
        status = "failure"
        task_logger.warning("rate_limited", detail="collect_product_task rate limit exceeded")
        _observe_metrics(start, "collect_product_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return

    # Validação e preparação do payload recebido
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
            result = scrape_monitored_product(db, url, UUID(user_id), payload)
            product_id = result.get("product_id", monitored_id)
            elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
            task_logger.info("collect_product_completed", duration_ms=elapsed_ms)
            redis_client.set("beat:last_success", datetime.now(timezone.utc).isoformat())
            circuit_breaker.record_success("collect_product_task")
            if product_id:
                adaptive_recheck.record_result(product_id, True)
        except HTTPException as http_err:
            status = "failure"
            SCRAPER_HEAD_FAILURES_TOTAL.inc()
            task_logger.error("collect_product_http_error", error=str(http_err), monitored_product_id=product_id, url=url)
            circuit_breaker.record_failure("collect_product_task")
            if product_id:
                adaptive_recheck.record_result(product_id, False)
                try:
                    crud_errors.create_scraping_error(
                        db,
                        UUID(product_id),
                        url,
                        str(http_err.detail),
                        ScrapingErrorType.http_error
                    )
                except Exception as err:
                    task_logger.warning("error_persist_failed", error=str(err))
            raise ScraperError(status_code=http_err.status_code, detail=str(http_err.detail))
        except Exception as exc:
            status = "failure"
            task_logger.error("collect_product_failed", error=str(exc))
            circuit_breaker.record_failure("collect_product_task")
            if product_id:
                adaptive_recheck.record_result(product_id, False)
                try:
                    crud_errors.create_scraping_error(
                        db,
                        UUID(product_id),
                        url,
                        str(exc),
                        ScrapingErrorType.parsing_error
                    )
                except Exception as err:
                    task_logger.warning("error_persist_failed", error=str(err))
        finally:
            if product_id:
                product = get_monitored_product_by_id(db, UUID(product_id))
                comparisons = (
                    get_latest_comparisons(db, UUID(product_id), limit=3) if product else []
                )
                if product:
                    next_time = adaptive_recheck.schedule_next(product, comparisons)
                    collect_product_task.apply_async(
                        eta=next_time,
                        kwargs={
                            "url": product.product_url,
                            "user_id": str(product.user_id),
                            "name_identification": product.name_identification,
                            "target_price": float(product.target_price),
                            "monitored_id": str(product.id)
                        }
                    )
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
    adaptive_recheck.redis = redis_client

    # Checa flag de suspensão global
    if is_scraping_suspended():
        task_logger.warning("suspended_via_flag", detail="scraping suspended flag is set")
        status = "failure"
        _observe_metrics(start, "collect_competitor_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return

    # Circuit breaker para evitar continuar se houver erros em sequência
    if not circuit_breaker.allow_request("collect_competitor_task"):
        status = "failure"
        task_logger.error("circuit_open", detail="circuit breaker open")
        _observe_metrics(start, "collect_competitor_task", status)
        SCRAPER_IN_FLIGHT.dec()
        return

    competitor_rate_limiter = RateLimiter(
        redis_key="rate:collect_competitor_task",
        max_requests=8,
        window_seconds=60
    )

    if not competitor_rate_limiter.allow_request():
        status = "failure"
        task_logger.warning("rate_limited", detail="collect_competitor_task rate limit exceeded")
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

    # Scraping propriamente dito e agendamento de comparação de preços
    with SessionLocal() as db:
        try:
            scrape_competitor_product(db, UUID(monitored_product_id), url, payload)
            elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
            task_logger.info("collect_competitor_completed", duration_ms=elapsed_ms)

            compare_prices_task.delay(str(monitored_product_id))
            task_logger.info("price_comparison_task_dispatched")
            circuit_breaker.record_success("collect_competitor_task")
            adaptive_recheck.record_result(monitored_product_id, True)

        except HTTPException as http_err:
            status = "failure"
            SCRAPER_HEAD_FAILURES_TOTAL.inc()
            task_logger.error("collect_competitor_http_error", error=str(http_err), monitored_product_id=monitored_product_id, url=url)
            circuit_breaker.record_failure("collect_competitor_task")
            adaptive_recheck.record_result(monitored_product_id, False)
            try:
                crud_errors.create_scraping_error(
                    db,
                    UUID(monitored_product_id),
                    url,
                    str(http_err.detail),
                    ScrapingErrorType.http_error
                )
            except Exception as err:
                task_logger.warning("error_persist_failed", error=str(err))
            raise ScraperError(status_code=http_err.status_code, detail=str(http_err.detail))

        except Exception as exc:
            status = "failure"
            task_logger.error("collect_competitor_failed", error=str(exc))
            circuit_breaker.record_failure("collect_competitor_task")
            adaptive_recheck.record_result(monitored_product_id, False)

        finally:
            try:
                product = get_monitored_product_by_id(db, UUID(monitored_product_id))
                comparisons = (
                    get_latest_comparisons(db, UUID(monitored_product_id), limit=3)
                    if product
                    else []
                )
                if product:
                    next_time = adaptive_recheck.schedule_next(product, comparisons)
                    collect_competitor_task.apply_async(
                        eta=next_time,
                        kwargs={
                            "monitored_product_id": str(product.id),
                            "url": url
                        },
                    )

            except Exception as exc:
                task_logger.warning("post_process_failed", error=str(exc))

            finally:
                _observe_metrics(start, "collect_competitor_task", status)
                SCRAPER_IN_FLIGHT.dec()
