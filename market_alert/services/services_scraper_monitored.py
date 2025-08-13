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

def scrape_monitored_product(
    db: Session,
    url: str,
    user_id: UUID,
    payload: MonitoredProductCreateScraping,
) -> dict:
    """ Realiza o scraping de produtos monitorados de forma síncrona """

    client = ScraperClient()
    details = asyncio.run(
        client.parse(
            url=url,
            product_type="monitored",
        )
    ) #Executa a coroutine do cliente assíncrono

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
