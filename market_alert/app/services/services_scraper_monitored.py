""" Fluxo de scraping dedicado a produtos monitorados

Este módulo fornece wrappers que delegam o trabalho pesado
para ``services_scraper_common``
"""

import structlog
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.utils.circuit_breaker import CircuitBreaker
from app.utils.rate_limiter import RateLimiter
from app.utils.block_recovery import BlockRecoveryManager

from app.schemas.schemas_products import MonitoredProductCreateScraping, MonitoredScrapedInfo
from app.crud.crud_monitored import create_or_update_monitored_product_scraped
from app.tasks.compare_prices_tasks import compare_prices_task

from market_scraper.app.services.services_scraper_common import (
    _scrape_product_common,
    scrape_product_common as _scrape_common_sync,
)
from market_scraper.app.utils.price import parse_price_str

#Logger especifico para o fluxo de monitorados
logger = structlog.get_logger("scraper_monitored_service")

async def _scrape_monitored_product(
        db: Session,
        url: str,
        user_id: UUID,
        payload: MonitoredProductCreateScraping,
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        recovery_manager: BlockRecoveryManager | None = None
) -> dict:
    """ Executa o scraping de um produto monitorado de forma assíncrona

    Esta função apenas repassa os parâmetros para ``_scrape_product_common``
    que contém toda a lógica utilizando Playwright para coletar o HTML
    """
    def persist(details: dict):
        product = create_or_update_monitored_product_scraped(
            db=db,
            user_id=user_id,
            product_data=payload,
            scraped_info=MonitoredScrapedInfo(
                current_price=parse_price_str(details.get("current_price"), url),
                thumbnail=details.get("thumbnail"),
                free_shipping=(details.get("shipping") == "Frete Grátis"),
            ),
            last_checked=datetime.now(timezone.utc),
        )
        compare_prices_task.delay(str(product.id))
        return product.id

    return await _scrape_product_common(
        url=url,
        user_id=user_id,
        payload=payload,
        product_type="monitored",
        persist_fn=persist,
        rate_limiter=rate_limiter,
        circuit_breaker=circuit_breaker,
        recovery_manager=recovery_manager,
    )

def scrape_monitored_product(
        db: Session,
        url: str,
        user_id: UUID,
        payload: MonitoredProductCreateScraping,
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        recovery_manager: BlockRecoveryManager | None = None
) -> dict:
    """ Versão síncrona utilizada pelas tasks Celery

    Internamente apenas chama ``scrape_product_common`` que
    executa a rotina assíncrona com Playwright
    """
    def persist(details: dict):
        product = create_or_update_monitored_product_scraped(
            db=db,
            user_id=user_id,
            product_data=payload,
            scraped_info=MonitoredScrapedInfo(
                current_price=parse_price_str(details.get("current_price"), url),
                thumbnail=details.get("thumbnail"),
                free_shipping=(details.get("shipping") == "Frete Grátis"),
            ),
            last_checked=datetime.now(timezone.utc),
        )
        compare_prices_task.delay(str(product.id))
        return product.id

    return _scrape_common_sync(
        url=url,
        user_id=user_id,
        payload=payload,
        product_type="monitored",
        persist_fn=persist,
        rate_limiter=rate_limiter,
        circuit_breaker=circuit_breaker,
        recovery_manager=recovery_manager,
    )
