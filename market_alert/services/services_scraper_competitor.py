""" Fluxo de scraping para produtos concorrentes

Este módulo utiliza o ``ScraperClient`` para consultar o serviço
``market_scraper`` e persistir localmente as informações do anúncio,
sem empregar gerenciador de bloqueios como ``RateLimiter`` ou
``CircuitBreaker``
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from uuid import UUID
import asyncio

import structlog
from sqlalchemy.orm import Session

from shared.schemas.products import CompetitorProductCreateScraping, CompetitorScrapedInfo

from market_alert.services.scraper_client import ScraperClient
from market_alert.crud.crud_competitor import create_or_update_competitor_product_scraped


#Logger específico para o scraping de concorrentes
logger = structlog.get_logger("scraper_competitor_service")

def scrape_competitor_product(
    db: Session,
    user_id: UUID,
    url: str,
    payload: CompetitorProductCreateScraping,
) -> dict:
    """ Realiza o scraping de concorrentes de forma síncrona """

    client = ScraperClient()
    details = asyncio.run(
        client.parse(
            url=url,
            product_type="competitor",
        )
    ) #Executa a coroutine do cliente assíncrono

    competitor = create_or_update_competitor_product_scraped(
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
        last_checked=datetime.now(timezone.utc),
    )
    return {"status": "success", "competitor_id": str(competitor.id)}
