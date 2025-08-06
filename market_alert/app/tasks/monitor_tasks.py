""" Tarefas agendadas para monitoramento periódico.

Estas tasks são executadas pelo Celery Beat e servem para despachar de forma
controlada novas coletas de produtos e concorrentes, além de acionar a
comparação de preços.
"""

from datetime import datetime, timezone
import time
import os

import structlog

from app.core.celery_app import celery_app
from infra.db import SessionLocal
from utils.circuit_breaker import CircuitBreaker
from utils.redis_client import get_redis_client, is_scraping_suspended
from utils.rate_limiter import RateLimiter
from app.utils.adaptive_recheck import AdaptiveRecheckManager
from market_scraper.app.core.config import settings as scraper_settings #Configurações do módulo de scraping

from app.enums.enums_products import MonitoringType
from app.crud.crud_monitored import get_products_by_type
from app.crud.crud_competitor import get_all_competitor_products
from app.tasks.scraper_tasks import collect_product_task, collect_competitor_task
from app.tasks.compare_prices_tasks import compare_prices_task
from app.metrics import SCRAPING_LATENCY_SECONDS

logger = structlog.get_logger("monitor_tasks")
redis_client = get_redis_client()

circuit_breaker = CircuitBreaker()
#Intervalo base definido nas configurações do scraper
adaptive_recheck = AdaptiveRecheckManager(
    base_interval=scraper_settings.ADAPTIVE_RECHECK_BASE_INTERVAL
)

#Batch sizes configurado via .env
BATCH_SIZE_SCRAPING = int(os.getenv("BATCH_SIZE_SCRAPING", "10"))
BATCH_SIZE_COMPETITOR = int(os.getenv("BATCH_SIZE_COMPETITOR", "20"))

#Rate limiters de taxa para o envio de sub tarefas do throttle manager
scraping_dispatch_limiter = RateLimiter(
    redis_key="rate:app.tasks.monitor_tasks.recheck_monitored_products",
    max_requests=BATCH_SIZE_SCRAPING,
    window_seconds=60
)
competitor_dispatch_limiter = RateLimiter(
    redis_key="rate:app.tasks.monitor_tasks.recheck_competitor_products",
    max_requests=BATCH_SIZE_COMPETITOR,
    window_seconds=60
)

@celery_app.task(name="app.tasks.monitor_tasks.recheck_monitored_products")
def recheck_monitored_products() -> None:
    """ Rechecagem periódica de produtos monitorados via scraping """
    start = time.time()
    status = "success"
    log = logger.bind(phase="recheck_scraping")

    # Circuit breaker: evita sobrecarga em caso de erros consecutivos
    if not circuit_breaker.allow_request("recheck_monitored_products"):
        log.error("circuit_open_skip_scraping", detail="circuit breaker open")
        return

    # Flag de suspensão global controlada via Redis
    if is_scraping_suspended():
        log.warning("suspended_via_flag", detail="scraping suspended flag is set")
        return

    # Rate limiter limita quantas tasks são despachadas por minuto
    if not scraping_dispatch_limiter.allow_request():
        log.warning("dispatch_rate_limited", detail="too many scraping dispatch calls")
        return

    with SessionLocal() as db:
        try:
            products = get_products_by_type(db, MonitoringType.scraping)
            due = [p for p in products if adaptive_recheck.should_recheck(str(p.id))]
            batch = due[:BATCH_SIZE_SCRAPING]

            for p in batch:
                log.info("dispatch_scraping_task", product_url=p.product_url, user_id=str(p.user_id))
                collect_product_task.delay(
                    url=p.product_url,
                    user_id=str(p.user_id),
                    name_identification=p.name_identification,
                    target_price=float(p.target_price)
                )

            elapsed_ms = int((time.time() - start) * 1000)
            log.info("recheck_monitored_completed", status=status, duration_ms=elapsed_ms, dispatched=len(batch))

            #Atualizar heartbeat
            redis_client.set("beat:last_scraping", datetime.now(timezone.utc).isoformat())

        except Exception as exc:
            status = "failure"
            elapsed_ms = int((time.time() - start) * 1000)
            log.error("recheck_monitored_failed", message=str(exc), duration_ms=elapsed_ms)
            raise

        finally:
            #Metricas Prometheus
            duration = time.time() - start
            SCRAPING_LATENCY_SECONDS.labels(source="monitor_scraper").observe(duration)

@celery_app.task(name="app.tasks.monitor_tasks.recheck_competitor_products")
def recheck_competitor_products():
    """ Rechecagem periódica de produtos concorrentes e comparação de preços """
    start = time.time()
    status = "success"
    log = logger.bind(phase="recheck_competitors")

    # Circuit breaker: evita sobrecarga em caso de erros consecutivos
    if not circuit_breaker.allow_request("recheck_competitor_products"):
        log.error("circuit_open_skip_competitors", detail="circuit breaker open")
        return

    # Flag de suspensão global controlada via Redis
    if is_scraping_suspended():
        log.warning("suspended_via_flag", detail="scraping suspended flag is set")
        return

    # Rate limiter limita quantas tasks são despachadas por minuto
    if not competitor_dispatch_limiter.allow_request():
        log.warning("dispatch_rate_limited", detail="too many competitor dispatch calls")
        return

    with SessionLocal() as db:
        try:
            competitors = get_all_competitor_products(db)
            batch = competitors[:BATCH_SIZE_COMPETITOR]
            monitored_ids = set()

            for c in batch:
                monitored_ids.add(c.monitored_product_id)
                log.info("recheck_competitor_item", monitored_id=str(c.monitored_product_id), url=c.product_url)
                #Dispara scraping do concorrente
                collect_competitor_task.delay(
                    monitored_id=str(c.monitored_product_id),
                    url=c.product_url
                )

            elapsed_ms = int((time.time() - start) * 1000)
            log.info("recheck_competitors_completed", status=status, duration_ms=elapsed_ms, count=len(batch))

            #Atualizar heartbeat
            redis_client.set("beat:last_competitor", datetime.now(timezone.utc).isoformat())

            #Dispara uma nova task de comparação para cada produto monitorado afetado
            for mp_id in monitored_ids:
                compare_prices_task.delay(str(mp_id))

        except Exception as exc:
            status = "failure"
            elapsed_ms = int((time.time() - start) * 1000)
            log.error("recheck_competitors_failed", message=str(exc), duration_ms=elapsed_ms)
            raise

        finally:
            #Métricas Prometheus
            duration = time.time() - start
            SCRAPING_LATENCY_SECONDS.labels(source="monitor_competitor").observe(duration)
