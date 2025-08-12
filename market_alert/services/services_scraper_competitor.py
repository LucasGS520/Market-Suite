""" Fluxo de scraping para produtos concorrentes

Este módulo utiliza o ``ScraperClient`` para consultar o serviço
``market_scraper`` e persistir localmente as informações do anúncio,
sem empregar gerenciador de bloqueios
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
from shared.schemas.products import CompetitorProductCreateScraping, CompetitorScrapedInfo

from market_alert.services.scraper_client import ScraperClient
from market_alert.crud.crud_competitor import create_or_update_competitor_product_scraped


#Logger específico para o scraping de concorrentes
logger = structlog.get_logger("scraper_competitor_service")

async def _scrape_competitor_product(
    db: Session,
    user_id: UUID,
    url: str,
    payload: CompetitorProductCreateScraping,
    rate_limiter: RateLimiter | None = None,
    circuit_breaker: CircuitBreaker | None = None,
) -> dict:
    """ Executa o scraping de concorrentes de forma assíncrona

    A comunicação ocorre via ``ScraperClient`` executado em ``thread``
    separada, sem empregar gerenciador de bloqueios.
    """

    #Requisição ao serviço de scraping em ``thread`` para evitar bloqueios
    details = await asyncio.to_thread(
        ScraperClient().parse,
        url=url,
        product_type="competitor",
    )

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
    rate_limiter: RateLimiter | None = None,
    circuit_breaker: CircuitBreaker | None = None,
) -> dict:
    """ Versão síncrona utilizada pelas tasks Celery

    Utiliza o ``ScraperClient`` para coletar dados sem qualquer
    gerenciador de bloqueios.
    """

    details = ScraperClient().parse(
        url=url,
        product_type="competitor",
    )

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
