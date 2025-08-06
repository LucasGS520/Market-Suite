""" Fluxo de scraping dedicado a produtos monitorados

O módulo comunica-se com o serviço externo ``market_scraper``
por HTTP, recebendo os dados já extraídos para apenas persistir
e acionar as comparações necessárias.
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from uuid import UUID

import httpx
import requests
import structlog
from sqlalchemy.orm import Session

from app.core.config import settings
from app.utils.circuit_breaker import CircuitBreaker
from app.utils.rate_limiter import RateLimiter
from app.utils.block_recovery import BlockRecoveryManager

from app.schemas.schemas_products import (
    MonitoredProductCreateScraping,
    MonitoredScrapedInfo,
)
from app.crud.crud_monitored import create_or_update_monitored_product_scraped
from app.tasks.compare_prices_tasks import compare_prices_task


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
    """ Executa o scraping de forma assíncrona via serviço externo """

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.SCRAPER_SERVICE_URL}/scraper/parse",
            json={"url": url, "product_type": "monitored"},
            timeout=30,
        )
        resp.raise_for_status()
        details = resp.json()

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
    recovery_manager: BlockRecoveryManager | None = None,
) -> dict:
    """ Versão síncrona utilizada pelas tasks Celery """

    resp = requests.post(
        f"{settings.SCRAPER_SERVICE_URL}/scraper/parse",
        json={"url": url, "product_type": "monitored"},
        timeout=30,
    )
    resp.raise_for_status()
    details = resp.json()

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
