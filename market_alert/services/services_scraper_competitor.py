""" Fluxo de scraping para produtos concorrentes """

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from shared.schemas.schemas_products import CompetitorProductCreateScraping, CompetitorScrapedInfo
from shared.schemas.schemas_scraper import ParserResponse

from market_alert.crud import crud_errors
from market_alert.crud.crud_competitor import create_or_update_competitor_product_scraped
from market_alert.models.models_products import CompetitorProduct
from market_alert.scraper.types import ScrapeResult
from market_alert.scraper.scraper_client import ScraperClient, ScraperClientError
from market_alert.utils._async_helpers import _run_sync
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
    
def _extract_metadata(payload: ParserResponse) -> dict[str, Any]:
    """ Agrupa metadados opcionais expostos pelo scraper """
    return payload.payload or {}
    
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

def _extract_float(value: Any) -> float | None:
    """ Converte valores numéricos opcionais em ``float`` """
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None
    
def _ensure_price(payload: ParserResponse, url: str) -> Decimal:
    """ Garante que o payload retornou preço válido """
    if payload.current_price is None:
        raise ScraperClientError(
            f"Payload do scraper sem preço para a URL {url}",
            status_code=500,
        )
    return payload.current_price

def _ensure_name(payload: ParserResponse, url: str) -> str:
    """ Valida presença de nome do produto antes de persistir """
    if payload.name is None:
        raise ScraperClientError(
            f"Payload do scraper sem nome para a URL {url}",
            status_code=500,
        )
    cleaned = payload.name.strip()
    if not cleaned:
        raise ScraperClientError(
            f"Nome vazio retornado pelo scraper para a URL {url}",
            status_code=500,
        )
    return cleaned

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
            product_type="competitor",
            user_id=user_id,
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
        
    payload_model = response.payload
    extras = _extract_metadata(payload_model)
    etag = extras.get("etag") or headers.get("etag")
    last_modified = _parse_last_modified(headers.get("last_modified") or headers.get("last-modified"))

    scraped_info = CompetitorScrapedInfo(
        name=_ensure_name(payload_model, url),
        current_price=_ensure_price(payload_model, url),
        old_price=_extract_decimal(extras.get("old_price")),
        thumbnail=extras.get("thumbnail"),
        free_shipping=bool(extras.get("free_shipping", False)),
        seller=extras.get("seller"),
        seller_rating=_extract_float(extras.get("seller_rating")),
        currency=extras.get("currency"),
    )

    competitor = create_or_update_competitor_product_scraped(
        db=db,
        product_data=payload,
        scraped_info=scraped_info,
        last_checked=now,
        currency=extras.get("currency"),
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
    return _run_sync(scrape_competitor_product_async(db, user_id, url, payload))
