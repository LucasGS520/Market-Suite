""" implementa o fluxo completo de scraping para produtos concorrentes

Este módulo define wrappers que delegam para ``services_scraper_common``
com o tipo ``competitor`` configurado
"""

import structlog
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.utils.circuit_breaker import CircuitBreaker
from app.utils.rate_limiter import RateLimiter
from app.utils.block_recovery import BlockRecoveryManager

from app.schemas.schemas_products import CompetitorProductCreateScraping, CompetitorScrapedInfo
from app.crud.crud_competitor import create_or_update_competitor_product_scraped
from market_scraper.app.utils.price import parse_price_str, parse_optional_price_str

from market_scraper.app.services.services_scraper_common import (
    _scrape_product_common,
    scrape_product_common as _scrape_common_sync,
)


#Logger específico para o scraping de concorrentes
logger = structlog.get_logger("scraper_competitor_service")

async def _scrape_competitor_product(
        db: Session,
        user_id: UUID,
        url: str,
        payload: CompetitorProductCreateScraping,
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        recovery_manager: BlockRecoveryManager | None = None
) -> dict:
    """ Executa o scraping de um produto concorrente de forma assíncrona

    Repassa os parâmetros para ``_scrape_product_common`` que usa Playwright
    para obtenção do HTML
    """
    def persist(details: dict):
        competitor = create_or_update_competitor_product_scraped(
            db=db,
            product_data=payload,
            scraped_info=CompetitorScrapedInfo(
                name=details.get("name", ""),
                current_price=parse_price_str(details.get("current_price"), url),
                old_price=parse_optional_price_str(details.get("old_price"), url),
                thumbnail=details.get("thumbnail"),
                free_shipping=(details.get("shipping") == "Frete Grátis"),
                seller=details.get("seller"),
                seller_rating=None,
            ),
            last_checked=datetime.now(timezone.utc),
        )
        return competitor.id

    return await _scrape_product_common(
        url=url,
        user_id=user_id,
        payload=payload,
        product_type="competitor",
        persist_fn=persist,
        rate_limiter=rate_limiter,
        circuit_breaker=circuit_breaker,
        recovery_manager=recovery_manager,
    )

def scrape_competitor_product(
        db: Session,
        user_id: UUID,
        url: str,
        payload: CompetitorProductCreateScraping,
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        recovery_manager: BlockRecoveryManager | None = None
) -> dict:
    """ Versão síncrona utilizada pelas tasks Celery

    Apenas chama ``scrape_product_common`` para executar o fluxo
    assíncrono através do Playwright
    """
    def persist(details: dict):
        competitor = create_or_update_competitor_product_scraped(
            db=db,
            product_data=payload,
            scraped_info=CompetitorScrapedInfo(
                name=details.get("name", ""),
                current_price=parse_price_str(details.get("current_price"), url),
                old_price=parse_optional_price_str(details.get("old_price"), url),
                thumbnail=details.get("thumbnail"),
                free_shipping=(details.get("shipping") == "Frete Grátis"),
                seller=details.get("seller"),
                seller_rating=None,
            ),
            last_checked=datetime.now(timezone.utc),
        )
        return competitor.id

    return _scrape_common_sync(
        url=url,
        user_id=user_id,
        payload=payload,
        product_type="competitor",
        persist_fn=persist,
        rate_limiter=rate_limiter,
        circuit_breaker=circuit_breaker,
        recovery_manager=recovery_manager,
    )
