""" Fluxo de scraping para produtos concorrentes

Este módulo consulta o serviço ``market_scraper`` para obter
os dados do anúncio e apenas realiza a persistência local.
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from uuid import UUID

import httpx
import structlog
from sqlalchemy.orm import Session

from alert_app.core.config import settings
from utils.circuit_breaker import CircuitBreaker
from utils.rate_limiter import RateLimiter
from alert_app.utils.block_recovery import BlockRecoveryManager
from utils.scraper_client import ScraperClient

from alert_app.schemas.schemas_products import (
    CompetitorProductCreateScraping,
    CompetitorScrapedInfo,
)
from alert_app.crud.crud_competitor import create_or_update_competitor_product_scraped


#Logger específico para o scraping de concorrentes
logger = structlog.get_logger("scraper_competitor_service")

async def _scrape_competitor_product(
    db: Session,
    user_id: UUID,
    url: str,
    payload: CompetitorProductCreateScraping,
    rate_limiter: RateLimiter | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    recovery_manager: BlockRecoveryManager | None = None,
) -> dict:
    """ Executa o scraping de concorrentes de forma assíncrona """

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.SCRAPER_SERVICE_URL}/scraper/parse",
            json={"url": url, "product_type": "competitor"},
            timeout=30,
        )
        resp.raise_for_status()
        details = resp.json()

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
    recovery_manager: BlockRecoveryManager | None = None
) -> dict:
    """ Versão síncrona utilizada pelas tasks Celery """

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
