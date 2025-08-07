""" Tarefas agendadas para monitoramento periódico.

As funções deste Módulo são executadas pelo Celery Beat e têm como objetivo
despachar novas coletas de produtos e concorrentes, além de iniciar a
comparação de preços.
"""

from datetime import datetime, timezone
import time
import os

import structlog

from alert_app.core.config import settings
from alert_app.core.celery_app import celery_app
from infra.db import SessionLocal
from utils.redis_client import get_redis_client, is_scraping_suspended

from alert_app.enums.enums_products import MonitoringType
from alert_app.crud.crud_monitored import get_products_by_type
from alert_app.crud.crud_competitor import get_all_competitor_products
from alert_app.tasks.scraper_tasks import collect_product_task, collect_competitor_task
from alert_app.tasks.compare_prices_tasks import compare_prices_task
from alert_app.metrics import SCRAPING_LATENCY_SECONDS


logger = structlog.get_logger("monitor_tasks")
redis_client = get_redis_client()

#Batch sizes configurado via .env
BATCH_SIZE_SCRAPING = int(os.getenv("BATCH_SIZE_SCRAPING", "10"))
BATCH_SIZE_COMPETITOR = int(os.getenv("BATCH_SIZE_COMPETITOR", "20"))

#Intervalo base usado para reagendamentos automáticos adaptativos
ADAPTIVE_RECHECK_BASE_INTERVAL = settings.ADAPTIVE_RECHECK_BASE_INTERVAL

@celery_app.task(name="alert_app.tasks.monitor_tasks.recheck_monitored_products")
def recheck_monitored_products() -> None:
    """ Rechecagem periódica de produtos monitorados via scraping """
    start = time.time()
    status = "success"
    log = logger.bind(phase="recheck_scraping")

    # Flag de suspensão global controlada via Redis
    if is_scraping_suspended():
        log.warning("suspended_via_flag", detail="scraping suspended flag is set")
        return

    with SessionLocal() as db:
        try:
            products = get_products_by_type(db, MonitoringType.scraping)
            batch = products[:BATCH_SIZE_SCRAPING]

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

@celery_app.task(name="alert_app.tasks.monitor_tasks.recheck_competitor_products")
def recheck_competitor_products():
    """ Rechecagem periódica de produtos concorrentes e comparação de preços """
    start = time.time()
    status = "success"
    log = logger.bind(phase="recheck_competitors")

    # Flag de suspensão global controlada via Redis
    if is_scraping_suspended():
        log.warning("suspended_via_flag", detail="scraping suspended flag is set")
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
