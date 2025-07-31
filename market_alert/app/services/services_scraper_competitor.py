""" implementa o fluxo completo de scraping para produtos concorrentes

Este módulo define wrappers que delegam para ``services_scraper_common``
com o tipo ``competitor`` configurado
"""

import structlog
from uuid import UUID

from sqlalchemy.orm import Session

from app.utils.circuit_breaker import CircuitBreaker
from app.utils.rate_limiter import RateLimiter
from app.utils.block_recovery import BlockRecoveryManager

from app.schemas.schemas_products import CompetitorProductCreateScraping

from app.services.services_scraper_common import (
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
    return await _scrape_product_common(
        db=db,
        url=url,
        user_id=user_id,
        payload=payload,
        product_type="competitor",
        rate_limiter=rate_limiter,
        circuit_breaker=circuit_breaker,
        recovery_manager=recovery_manager
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
    return _scrape_common_sync(
        db=db,
        url=url,
        user_id=user_id,
        payload=payload,
        product_type="competitor",
        rate_limiter=rate_limiter,
        circuit_breaker=circuit_breaker,
        recovery_manager=recovery_manager
    )
