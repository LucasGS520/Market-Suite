""" Tarefas agendadas para monitoramento periódico.

As funções deste Módulo são executadas pelo Celery Beat e têm como objetivo
despachar novas coletas de produtos e concorrentes, além de iniciar a
comparação de preços.
"""

from datetime import datetime, timezone
from decimal import Decimal
import time
import os
import asyncio

import structlog

from shared.infra.db import SessionLocal
from shared.metrics.metrics_scraper import SCRAPING_LATENCY_SECONDS
from shared.utils.redis_client import get_redis_client, is_scraping_suspended
from shared.schemas.schemas_products import MonitoredProductCreateScraping, MonitoredScrapedInfo, CompetitorProductCreateScraping, CompetitorScrapedInfo

from market_alert.core.config_alert import settings
from market_alert.core.celery_app import celery_app
from market_alert.enums.enums_products import MonitoringType
from market_alert.crud.crud_monitored import get_products_by_type, create_or_update_monitored_product_scraped
from market_alert.crud.crud_competitor import get_all_competitor_products, create_or_update_competitor_product_scraped
from market_alert.tasks.compare_prices_tasks import compare_prices_task
from market_alert.services.scraper_client import ScraperClient, ScraperClientError


logger = structlog.get_logger("monitor_tasks")
redis_client = get_redis_client()
scraper_client = ScraperClient()

#Limite de concorrência para chamadas ao serviço de scraping
MAX_SCRAPER_CONCURRENCY = int(os.getenv("MAX_SCRAPER_CONCURRENCY", "5"))

#Tamanho dos lotes para rechecagens de produtos e concorrentes
BATCH_SIZE_SCRAPING = int(os.getenv("BATCH_SIZE_SCRAPING", "10"))
BATCH_SIZE_COMPETITOR = int(os.getenv("BATCH_SIZE_COMPETITOR", "20"))

#Intervalo base usado para reagendamentos automáticos adaptativos
ADAPTIVE_RECHECK_BASE_INTERVAL = settings.ADAPTIVE_RECHECK_BASE_INTERVAL

async def _parse_monitored_batch(products):
    """ Executa o parsing de produtos monitorados de forma concorrente """

    semaphore = asyncio.Semaphore(MAX_SCRAPER_CONCURRENCY)

    async def _fetch(p):
        log = logger.bind(monitored_id=str(p.id))
        log.info("chamada_market_scraper", product_url=p.product_url)
        async with semaphore:
            try:
                details = await scraper_client.parse(
                    url=p.product_url,
                    product_type="monitored",
                    monitored_id=str(p.id),
                )
                return {"product": p, "details": details, "error": None}
            except ScraperClientError as exc:
                return {"product": p, "details": None, "error": exc}

    tasks = [_fetch(p) for p in products]
    return await asyncio.gather(*tasks)

async def _parse_competitor_batch(competitors):
    """ Executa o parsing de concorrentes de forma concorrente """

    semaphore = asyncio.Semaphore(MAX_SCRAPER_CONCURRENCY)

    async def _fetch(c):
        log = logger.bind(competitor_id=str(c.id))
        log.info("chamada_market_scraper", product_url=c.product_url)
        async with semaphore:
            try:
                details = await scraper_client.parse(
                    url=c.product_url,
                    product_type="competitor",
                )
                return {"competitor": c, "details": details, "error": None}
            except ScraperClientError as exc:
                return {"competitor": c, "details": None, "error": exc}

    tasks = [_fetch(c) for c in competitors]
    return await asyncio.gather(*tasks)

@celery_app.task(name="market_alert.tasks.monitor_tasks.recheck_monitored_products")
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

            #Executa o scraping de forma concorrente
            results = asyncio.run(_parse_monitored_batch(batch))

            for result in results:
                p = result["product"]
                if result["error"] is not None:
                    status = "failure"
                    log.error(
                        "scraper_request_failed",
                        error=str(result["error"]),
                        url=p.product_url,
                    )
                    continue

                details = result["details"]

                #Salva os dados atualizados no banco e guarda preço anterior para verificar se houve mudança
                old_price = p.current_price
                product = create_or_update_monitored_product_scraped(
                    db=db,
                    user_id=p.user_id,
                    product_data=MonitoredProductCreateScraping(
                        name_identification=p.name_identification,
                        product_url=p.product_url,
                        target_price=p.target_price,
                    ),
                    scraped_info=MonitoredScrapedInfo(
                        current_price=Decimal(str(details.get("current_price", 0))),
                        thumbnail=details.get("thumbnail"),
                        free_shipping=details.get("free_shipping", False),
                    ),
                    last_checked=datetime.now(timezone.utc),
                )

                #Agendamento da comparação apenas se houver mudança no preço
                if old_price != product.current_price:
                    compare_prices_task.delay(str(product.id))

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

@celery_app.task(name="market_alert.tasks.monitor_tasks.recheck_competitor_products")
def recheck_competitor_products():
    """ Rechecagem periódica de produtos concorrentes e comparação de preços """
    start = time.time()
    status = "success"
    log = logger.bind(phase="recheck_competitors")

    # Flag de suspensão global controlada via Redis
    if is_scraping_suspended():
        log.warning("suspended_via_flag", detail="scraping suspended flag is set")
        return

    with (SessionLocal() as db):
        try:
            competitors = get_all_competitor_products(db)
            batch = competitors[:BATCH_SIZE_COMPETITOR]
            updated_ids = set()

            # Executa o scraping de forma concorrente
            results = asyncio.run(_parse_competitor_batch(batch))

            for result in results:
                c = result["competitor"]
                if result["error"] is not None:
                    status = "failure"
                    log.error(
                        "scraper_competitor_failed",
                        error=str(result["error"]),
                        url=c.product_url,
                    )
                    continue

                details = result["details"]

                old_price = c.current_price
                competitor = create_or_update_competitor_product_scraped(
                    db=db,
                    product_data=CompetitorProductCreateScraping(
                        monitored_product_id=c.monitored_product_id,
                        product_url=c.product_url,
                    ),
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
                    last_checked=datetime.now(timezone.utc),
                )

                if old_price != competitor.current_price:
                    updated_ids.add(competitor.monitored_product_id)

            elapsed_ms = int((time.time() - start) * 1000)
            log.info("recheck_competitors_completed", status=status, duration_ms=elapsed_ms, count=len(batch))

            #Atualizar heartbeat
            redis_client.set("beat:last_competitor", datetime.now(timezone.utc).isoformat())

            #Dispara uma nova task de comparação para cada produto monitorado com mudança de preço
            for mp_id in updated_ids:
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
