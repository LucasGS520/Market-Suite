""" Fluxo de scraping para produtos concorrentes """

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from shared.schemas.schemas_products import CompetitorProductCreateScraping, CompetitorScrapedInfo

from market_alert.crud import crud_errors
from market_alert.crud.crud_competitor import create_or_update_competitor_product_scraped
from market_alert.models.models_products import CompetitorProduct
from market_alert.schemas.schemas_scraper_payload import ScraperPayload
from market_alert.scraper.types import ScrapeResult
from market_alert.scraper.scraper_client import ScraperClient, ScraperClientError
from shared.enums.error_codes import ScrapingErrorType


#Logger específico para o scraping de concorrentes
logger = structlog.get_logger("scraper_competitor_service")

def _parse_last_modified(header: str | None) -> datetime | None:
    """ Converte cabeçalho ``Last-Modified`` em ``datetime`` UTC """
    if not header:
        return None
    try:
        dt = parsedate_to_datetime(header)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None
    
def _get_existing(db: Session, payload: CompetitorProductCreateScraping) -> CompetitorProduct | None:
    """ Recupera concorrente já persistido para reaproveitar metdados """
    return (
        db.query(CompetitorProduct)
        .filter(
            CompetitorProduct.monitored_product_id == payload.monitored_product_id,
            CompetitorProduct.product_url == str(payload.product_url).strip(),
        )
        .first()
    )

def _extract_decimal(value: Any) -> Decimal | None:
    """ Converte valores numéricos opcionais em ``Decimal`` com tolerância """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None

async def scrape_competitor_product_async(
    db: Session,
    user_id: UUID,
    url: str,
    payload: CompetitorProductCreateScraping,
) -> ScrapeResult:
    """ Executa scraping de concorrentes retornando ``ScraperResult`` estruturado """
    existing = _get_existing(db, payload)
    etag = existing.etag if existing else None
    last_modified = existing.last_modified if existing else None
    
    async with ScraperClient() as client:
        response = await client.fetch(
            url=url,
            monitored_id=str(payload.monitored_product_id),
            etag=etag,
            last_modified=last_modified,
        )

    headers = {k.lower(): v for k, v in response.headers.items()}
    status_code = response.status_code
    now = datetime.now(timezone.utc)

    if status_code == 304:
        if existing:
            existing.last_checked = now
            db.commit()
        return ScrapeResult(
            status="not_modified",
            product_id=str(existing.id) if existing else None,
            http_status=304,
        )

    if status_code == 422 and response.error_code == "no_result":
        crud_errors.create_scraping_error(
            db,
            payload.monitored_product_id,
            url,
            "pipeline retornou no_result",
            ScrapingErrorType.no_result,
        )
        return ScrapeResult(
            status="no_result",
            product_id=str(existing.id) if existing else None,
            http_status=422,
            error_code="no_result",
        )

    if status_code != 200 or response.payload is None:
        raise ScraperClientError(
            "Resposta inesperada ao coletar concorrente",
            status_code=status_code,
        )
        
    payload_model = ScraperPayload.model_validate(response.payload)
    etag = payload_model.etag or headers.get("etag")
    last_modified = payload_model.last_modified or _parse_last_modified(headers.get("last-modified"))

    scraped_info = CompetitorScrapedInfo(
        name=payload_model.name,
        current_price=payload_model.current_price,
        old_price=_extract_decimal(response.payload.get("old_price")),
        thumbnail=response.payload.get("thumbnail"),
        free_shipping=bool(response.payload.get("free_shipping", False)),
        seller=response.payload.get("seller"),
        seller_rating=response.payload.get("seller_rating"),
        currency=payload_model.currency,
    )

    competitor = create_or_update_competitor_product_scraped(
        db=db,
        product_data=payload,
        scraped_info=scraped_info,
        last_checked=now,
        currency=payload_model.currency,
        etag=etag,
        last_modified=last_modified,
    )

    return ScrapeResult(
        status="success",
        product_id=str(competitor.id),
        price_changed=bool(getattr(competitor, "_price_changed", True)),
        http_status=200,
    )

def scrape_competitor_product(
    db: Session,
    user_id: UUID,
    url: str,
    payload: CompetitorProductCreateScraping,
) -> ScrapeResult:
    """ Executa scaping de forma síncrona reutilizando o loop atual """
    coro = scrape_competitor_product_async(db, user_id, url, payload)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    if loop.is_running():
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()

    return loop.run_until_complete(coro)
