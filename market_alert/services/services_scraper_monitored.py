""" Fluxo de scraping dedicado a produtos monitorados """

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from shared.schemas.schemas_products import MonitoredProductCreateScraping, MonitoredScrapedInfo

from market_alert.core.config_alert import settings
from market_alert.crud import crud_errors
from market_alert.crud.crud_monitored import (
    create_or_update_monitored_product_scraped,
    get_monitored_product_by_user_and_url,
)
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.schemas.schemas_scraper_payload import ScraperPayload
from market_alert.scraper.types import ScrapeResult
from market_alert.scraper.scraper_client import ScraperClient, ScraperClientError, ScraperFetchResult
from market_alert.tasks.compare_prices_tasks import compare_prices_task
from shared.enums.error_codes import ScrapingErrorType


#Logger especifico para o fluxo de monitorados
logger = structlog.get_logger("scraper_monitored_service")

def _parse_last_modified(header_value: str | None) -> datetime | None:
    """ Converte cabeçalho HTTP ``Last-Modified`` em ``datetime`` """
    if not header_value:
        return None
    try:
        dt = parsedate_to_datetime(header_value)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None
    
async def _handle_response(
    db: Session,
    user_id: UUID,
    monitored_payload: MonitoredProductCreateScraping,
    fetch_result: ScraperFetchResult,
    *,
    headers: dict[str, str],
    existing_id: UUID | None,
    last_checked: datetime,
) -> ScrapeResult:
    """ Processa reposta recebida atualizando banco e gerando histórico """
    status_code = fetch_result.status_code
    if status_code == 304:
        if existing_id:
            product = get_monitored_product_by_user_and_url(db, user_id, str(monitored_payload.product_url))
            if product:
                product.last_checked = last_checked
                product.status = MonitoredStatus.active
                db.commit()
        return ScrapeResult(status="not_modified", product_id=str(existing_id) if existing_id else None, http_status=304)
    
    if status_code == 422 and fetch_result.error_code == "no_result":
        return ScrapeResult(
            status="no_result",
            product_id=str(existing_id) if existing_id else None,
            http_status=422,
            error_code="no_result",
        )

    if status_code != 200 or fetch_result.payload is None:
        raise ScraperClientError(
            "Resposta inesperada do scraper ao processar monitorado",
            status_code=status_code,
        )

    payload = ScraperPayload.model_validate(fetch_result.payload)
    normalized_headers = {k.lower(): v for k, v in headers.items()}
    etag = payload.etag or normalized_headers.get("etag")
    last_modified = payload.last_modified or _parse_last_modified(normalized_headers.get("last-modified"))

    scraped_info = MonitoredScrapedInfo(
        current_price=payload.current_price,
        thumbnail=fetch_result.payload.get("thumbnail"),
        free_shipping=bool(fetch_result.payload.get("free_shipping", False)),
        currency=payload.currency,
    )

    product = create_or_update_monitored_product_scraped(
        db=db,
        user_id=user_id,
        product_data=monitored_payload,
        scraped_info=scraped_info,
        last_checked=last_checked,
        currency=payload.currency,
        etag=etag,
        last_modified=last_modified,
    )

    price_changed = bool(getattr(product, "_price_changed", True))

    if price_changed:
        compare_prices_task.delay(str(product.id))

    return ScrapeResult(
        status="success",
        product_id=str(product.id),
        price_changed=price_changed,
        http_status=200,
    )

async def scrape_monitored_product_async(
    db: Session,
    url: str,
    user_id: UUID,
    payload: MonitoredProductCreateScraping,
) -> ScrapeResult:
    """ Executa fluxo de scraping para produto monitorado de forma assíncrona """
    existing = get_monitored_product_by_user_and_url(db, user_id, str(payload.product_url))
    etag = existing.etag if existing else None
    last_modified = existing.last_modified if existing else None

    now = datetime.now(timezone.utc)
    force_refresh = False
    if existing and existing.last_checked:
        delta = (now - existing.last_checked).total_seconds()
        force_refresh = delta >= settings.SCRAPER_FORCE_REFRESH_TTL_SECONDS

    async with ScraperClient() as client:
        result = await client.fetch(
            url=url,
            monitored_id=str(existing.id) if existing else None,
            etag=etag,
            last_modified=last_modified,
            force_refresh=force_refresh,
        )
        
    headers = dict(result.headers)
    outcome = await _handle_response(
        db,
        user_id,
        payload,
        result,
        headers=headers,
        existing_id=existing.id if existing else None,
        last_checked=now,
    )

    if outcome.status == "no_result" and existing:
        crud_errors.create_scraping_error(
            db,
            existing.id,
            url,
            "pipeline retornou no_result",
            ScrapingErrorType.no_result,
        )
    return outcome

def scrape_monitored_product(
    db: Session,
    url: str,
    user_id: UUID,
    payload: MonitoredProductCreateScraping,
) -> ScrapeResult:
    """ Executa o scraping de forma síncrona reutilizando o loop corrente """
    coro = scrape_monitored_product_async(db, url, user_id, payload)

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
