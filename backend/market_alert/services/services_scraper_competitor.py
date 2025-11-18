""" Fluxo de scraping para produtos concorrentes """

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from backend.shared.schemas.shared_schemas_products import CompetitorProductCreateScraping, CompetitorScrapedInfo
from backend.shared.schemas.shared_schemas_scraper import ScrapeResult

from shared.utils import sanitize_media_url, sanitize_text, extract_scraper_metadata
from shared.utils.url_validation import canonicalize_product_url
from market_alert.crud.crud_competitor import (
    create_or_update_competitor_product_scraped,
    get_competitor_by_monitored_and_url,
)
from market_alert.models.models_products import CompetitorProduct
from market_alert.scraper.scraper_client import ScraperClient, ScraperClientError
from market_alert.utils._async_helpers import _run_sync
from market_alert.services._scraper_common import (
    execute_scraper_fetch,
    ensure_name,
    ensure_price,
    normalize_currency_code,
    resolve_conditional_headers,
    to_decimal,
    to_float,
)


#Logger específico para o scraping de concorrentes
logger = structlog.get_logger("scraper_competitor_service")
    
def _get_existing(db: Session, payload: CompetitorProductCreateScraping) -> CompetitorProduct | None:
    """ Recupera concorrente já persistido para reaproveitar metdados """
    return get_competitor_by_monitored_and_url(
        db,
        payload.monitored_product_id,
        str(payload.product_url),
    )

async def scrape_competitor_product_async(
    db: Session,
    user_id: UUID,
    url: str,
    payload: CompetitorProductCreateScraping,
) -> ScrapeResult:
    """ Executa scraping de concorrentes retornando ``ScraperResult`` estruturado """
    try:
        normalized_url = canonicalize_product_url(str(url))
    except ValueError:
        normalized_url = str(url)
    existing = _get_existing(db, payload)
    etag, last_modified = resolve_conditional_headers(existing)

    async with ScraperClient() as client:
        response = await execute_scraper_fetch(
            client,
            url=normalized_url,
            monitored_id=str(payload.monitored_product_id),
            etag=etag,
            last_modified=last_modified,
            force_refresh=False,
            product_type="competitor",
            user_id=user_id,
            metadata=None,
        )

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
        
    payload_model = response.payload
    metadata = extract_scraper_metadata(payload_model, response.headers)

    sanitized_thumbnail = sanitize_media_url(metadata.get("thumbnail"))
    sanitized_currency = normalize_currency_code(metadata.get("currency"))
    sanitized_seller = sanitize_text(metadata.get("seller"))

    scraped_info = CompetitorScrapedInfo(
        name=ensure_name(payload_model, normalized_url),
        product_url=normalized_url,
        current_price=ensure_price(payload_model, normalized_url),
        old_price=to_decimal(metadata.get("old_price")),
        thumbnail=sanitized_thumbnail,
        free_shipping=bool(metadata.get("free_shipping", False)),
        seller=sanitized_seller,
        seller_rating=to_float(metadata.get("seller_rating")),
        currency=sanitized_currency,
        collected_at=now,
    )

    competitor = create_or_update_competitor_product_scraped(
        db=db,
        product_data=payload,
        scraped_info=scraped_info,
        last_checked=now,
        currency=sanitized_currency,
        etag=metadata.etag,
        last_modified=metadata.last_modified,
    )

    return ScrapeResult(
        status="success",
        product_id=str(competitor.id),
        price_changed=bool(getattr(competitor, "_price_changed", True)),
        availability_changed=bool(getattr(competitor, "_availability_changed", True)),
        http_status=200,
    )

def scrape_competitor_product(
    db: Session,
    user_id: UUID,
    url: str,
    payload: CompetitorProductCreateScraping,
) -> ScrapeResult:
    """ Executa scaping de forma síncrona reutilizando o loop atual """
    return _run_sync(scrape_competitor_product_async(db, user_id, url, payload))
