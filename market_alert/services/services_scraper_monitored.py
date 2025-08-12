""" Fluxo de scraping dedicado a produtos monitorados

A comunicação com o serviço externo ``market_scraper`` é realizada
exclusivamente via ``ScraperClient`` para persistir os dados
e acionar as comparações necessárias, sem uso de gerenciador
de bloqueios.
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from uuid import UUID
import asyncio

import structlog
from sqlalchemy.orm import Session

from shared.utils.circuit_breaker import CircuitBreaker
from shared.utils.rate_limiter import RateLimiter
from market_alert.services.scraper_client import ScraperClient

from market_alert.schemas.schemas_products import (
    MonitoredProductCreateScraping,
    MonitoredScrapedInfo,
)
from market_alert.crud.crud_monitored import create_or_update_monitored_product_scraped
from market_alert.tasks.compare_prices_tasks import compare_prices_task


#Logger especifico para o fluxo de monitorados
logger = structlog.get_logger("scraper_monitored_service")

async def _scrape_monitored_product(
    db: Session,
    url: str,
    user_id: UUID,
    payload: MonitoredProductCreateScraping,
    rate_limiter: RateLimiter | None = None,
    circuit_breaker: CircuitBreaker | None = None,
) -> dict:
    """ Executa o scraping de forma assíncrona usando ``ScraperClient``

    A chamada síncrona é executada em ``thread`` separada para não
    bloquear o loop de eventos, e não há mais uso de gerenciador
    de bloqueios.
    """

    #Dispara o cliente de scraping em ``thread`` separada
    details = await asyncio.to_thread(
        ScraperClient().parse,
        url=url,
        product_type="monitored",
    )

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
    rate_limiter: RateLimiter | None = None,
    circuit_breaker: CircuitBreaker | None = None,
) -> dict:
    """ Versão síncrona utilizada pelas tasks Celery

    Realiza a requisição via ``ScraperClient`` sem
    utilizar ``BlockRecoveryManager``
    """

    details = ScraperClient().parse(
        url=url,
        product_type="monitored",
    )

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
