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

from shared.schemas.schemas_products import CompetitorProductCreateScraping, CompetitorScrapedInfo

from market_alert.scraper.scraper_client import ScraperClient
from market_alert.crud.crud_competitor import create_or_update_competitor_product_scraped


#Logger específico para o scraping de concorrentes
logger = structlog.get_logger("scraper_competitor_service")

async def scrape_competitor_product_async(
    db: Session,
    user_id: UUID,
    url: str,
    payload: CompetitorProductCreateScraping,
) -> dict:
    """ Executa o scraping de concorrentes de forma assíncrona

    Utiliza ``ScraperClient`` em um bloco de contexto assíncrono
    para assegurar que a sessão HTTP seja fechada ao término
    """
    async with ScraperClient() as client:
        #Fecha automaticamente a conexão HTTP ao sair do contexto
        details = await client.parse(url=url, product_type="competitor")

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

def scrape_competitor_product(
    db: Session,
    user_id: UUID,
    url: str,
    payload: CompetitorProductCreateScraping,
) -> dict:
    """ Interface síncrona que reutiliza o loop de eventos quando disponível """

    coro = scrape_competitor_product_async(db, user_id, url, payload)

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
