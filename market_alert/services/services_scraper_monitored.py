""" Fluxo de scraping dedicado a produtos monitorados

Este módulo se comunica com o serviço externo ``market_scraper``
exclusivamente via ``ScraperClient`` para persistir os dados e
acionar as comparações necessárias, sem empregar mecanismos
de rate limiting ou circuit breaker.
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from uuid import UUID
import asyncio

import structlog
from sqlalchemy.orm import Session

from shared.schemas.products import MonitoredProductCreateScraping, MonitoredScrapedInfo

from market_alert.services.scraper_client import ScraperClient
from market_alert.crud.crud_monitored import create_or_update_monitored_product_scraped
from market_alert.tasks.compare_prices_tasks import compare_prices_task


#Logger especifico para o fluxo de monitorados
logger = structlog.get_logger("scraper_monitored_service")

async def scrape_monitored_product_async(
    db: Session,
    url: str,
    user_id: UUID,
    payload: MonitoredProductCreateScraping,
) -> dict:
    """ Executa o scraping de produtos monitorados de forma assíncrona

    Utiliza ``ScraperClient`` como gerenciador de contexto para garantir o
    fechamento da sessão HTTP após o uso.
    """
    async with ScraperClient() as client:
        #Garante que a conexão HTTP seja encerrada ao final do bloco
        details = await client.parse(url=url, product_type="monitored")

        product = create_or_update_monitored_product_scraped(
            db=db,
            user_id=user_id,
            product_data=payload,
            scraped_info=MonitoredScrapedInfo(
                current_price=Decimal(str(details.get("current_price", 0))),
                thumbnail=details.get("thumbnail"),
                free_shipping=details.get("free_shipping", False),
            ),
            last_checked=datetime.now(timezone.utc),
        )
        compare_prices_task.delay(str(product.id))
        return {"status": "success", "product_id": str(product.id)}

def scrape_monitored_product(
    db: Session,
    url: str,
    user_id: UUID,
    payload: MonitoredProductCreateScraping,
) -> dict:
    """ Executa o scraping em contexto síncrono """

    coro = scrape_monitored_product_async(db, url, user_id, payload)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)

    if loop.is_running():
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()

    else:
        return loop.run_until_complete(coro)
