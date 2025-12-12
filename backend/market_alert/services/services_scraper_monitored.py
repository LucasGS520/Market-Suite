""" Fluxo de scraping dedicado a produtos monitorados """

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from backend.shared.schemas.shared_schemas_products import MonitoredProductCreateScraping, MonitoredScrapedInfo
from backend.shared.schemas.shared_schemas_scraper import ScrapeResult
from shared.utils import sanitize_media_url, sanitize_text, extract_scraper_metadata
from shared.utils.url_validation import normalize_product_url

from market_alert.core.config_alert import settings
from market_alert.crud.crud_monitored import (
    create_or_update_monitored_product_scraped,
    get_monitored_product_by_user_and_url,
    _compute_next_check_at,
)
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.scraper.scraper_client import ScraperClient, ScraperClientError, ScraperFetchResult
from market_alert.services._scraper_common import (
    compute_force_refresh,
    ensure_price,
    execute_scraper_fetch,
    normalize_currency_code,
    resolve_conditional_headers,
)


#Logger específico para o fluxo de monitorados
logger = structlog.get_logger("scraper_monitored_service")

def _handle_response(
    db: Session,
    user_id: UUID,
    monitored_payload: MonitoredProductCreateScraping,
    fetch_result: ScraperFetchResult,
    *,
    existing_id: UUID | None,
    last_checked: datetime,
    request_url: str,
) -> ScrapeResult:
    """ Processa reposta do scraper e retorna ``ScrapeResult`` padronizado

    O collector espera sempre um dos status suportados em
    :class:`ScrapeResult`. Este método converte códigos HTTP e payloads do
    scraper no contrato consumido pelas tasks, preservando `http_status`,
    `price_changed` e `availability_changed`. 
    """
    status_code = fetch_result.status_code
    if status_code == 304:
        if existing_id:
            try:
                lookup_url = normalize_product_url(str(monitored_payload.product_url))
            except ValueError:
                lookup_url = str(monitored_payload.product_url)

            product = get_monitored_product_by_user_and_url(
                db,
                user_id,
                lookup_url,
            )
            if product:
                product.last_checked = last_checked
                product.last_scraped_at = last_checked
                product.status = MonitoredStatus.active
                product.next_check_at = _compute_next_check_at(product, last_checked)
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

    payload = fetch_result.payload
    metadata = extract_scraper_metadata(payload, fetch_result.headers)
    sanitized_name = sanitize_text(payload.name)

    sanitized_thumbnail = sanitize_media_url(metadata.get("thumbnail"))
    sanitized_currency = normalize_currency_code(metadata.get("currency"))
    availability = metadata.get("availability")

    scraped_info = MonitoredScrapedInfo(
        name=sanitized_name or sanitize_text(monitored_payload.name_identification) or request_url,
        product_url=request_url,
        current_price=ensure_price(payload, request_url),
        thumbnail=sanitized_thumbnail,
        free_shipping=bool(metadata.get("free_shipping", False)),
        currency=sanitized_currency,
        collected_at=last_checked,
        availability=bool(availability) if availability is not None else None,
    )

    product = create_or_update_monitored_product_scraped(
        db=db,
        user_id=user_id,
        product_data=monitored_payload,
        scraped_info=scraped_info,
        last_checked=last_checked,
        currency=sanitized_currency,
        etag=metadata.etag,
        last_modified=metadata.last_modified,
        scraped_name=sanitized_name,
    )

    price_changed = bool(getattr(product, "_price_changed", True))
    availability_changed = bool(getattr(product, "_availability_changed", True))

    return ScrapeResult(
        status="success",
        product_id=str(product.id),
        price_changed=price_changed,
        availability_changed=availability_changed,
        http_status=200,
    )

def scrape_monitored_product(
    db: Session,
    url: str,
    user_id: UUID,
    payload: MonitoredProductCreateScraping,
) -> ScrapeResult:
    """ Executa scraping para produto monitorado de forma síncrona

    Retorna sempre um :class:`ScrapeResult` com status dentro do contrato
    compartilhado (`success`, `not_modified`, `no_result`, `error`). A URL
    é normalizada antes do fetch e o ETag/Last-Modified existente é reaproveitado
    para permitir retornos `not_modified` consistentes.
    """
    try:
        normalized_url = normalize_product_url(str(url))
    except ValueError:
        normalized_url = str(url)

    try:
        lookup_payload_url = normalize_product_url(str(payload.product_url))
    except ValueError:
        lookup_payload_url = str(payload.product_url)

    existing = get_monitored_product_by_user_and_url(
        db,
        user_id,
        lookup_payload_url,
    )
    etag, last_modified = resolve_conditional_headers(existing)

    now = datetime.now(timezone.utc)
    last_checked_ref = getattr(existing, "last_checked", None)
    force_refresh = compute_force_refresh(
        last_checked_ref if isinstance(last_checked_ref, datetime) else None,
        now=now,
        ttl_seconds=settings.SCRAPER_FORCE_REFRESH_TTL_SECONDS,
    ) if existing else False

    with ScraperClient() as client:
        result = execute_scraper_fetch(
            client,
            url=normalized_url,
            monitored_id=str(existing.id) if existing else None,
            etag=etag,
            last_modified=last_modified,
            force_refresh=force_refresh,
            product_type="monitored",
            user_id=user_id,
            metadata=None,
        )

    outcome = _handle_response(
        db,
        user_id,
        payload,
        result,
        existing_id=existing.id if existing else None,
        last_checked=now,
        request_url=normalized_url,
    )

    return outcome
