""" Fluxo de scraping para produtos concorrentes """

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from shared.schemas.shared_schemas_products import CompetitorProductCreateScraping, CompetitorScrapedInfo
from shared.schemas.shared_schemas_scraper import ScrapeResult
from shared.clients.scraper.scraper_client import ScraperClient, ScraperClientError
from shared.utils import (
    sanitize_media_url,
    sanitize_text,
    extract_scraper_metadata,
)
from shared.utils.url_validation import normalize_competitor_url

from market_alert.models.models_products import CompetitorProduct
from market_alert.products.crud.crud_competitor import create_or_update_competitor_product_scraped, get_competitor_by_monitored_and_url
from market_alert.collectors.services.scraper_common import (
    execute_scraper_fetch,
    ensure_name,
    ensure_price,
    handle_not_modified_response,
    normalize_currency_code,
    resolve_availability,
    resolve_conditional_headers,
    to_decimal,
    to_float,
)
from market_alert.comparisons.utils.price_comparator import request_comparison_recompute


#Logger específico para o scraping de concorrentes
logger = structlog.get_logger("scraper_competitor_service")
    
def _get_existing(
    db: Session,
    payload: CompetitorProductCreateScraping,
    normalized_url: str,
) -> CompetitorProduct | None:
    """ Recupera concorrente já persistido reutilizando a URL canônica 
    
    A busca centraliza a reutilização do ETag/Last-Modified para permitir
    retornos `not_modified` coerentes no contrato de `ScrapeResult`.
    """
    return get_competitor_by_monitored_and_url(
        db,
        payload.monitored_product_id,
        normalized_url,
    )

def _normalize_competitor_scrape_url(url: str) -> str:
    """ Normalize a URL do concorrente para alinhar fetch e persistência """
    normalized = normalize_competitor_url(url)
    if not normalized:
        #Garante previsibilidade mesmo quando a URL original é inválida
        return str(url).strip()
    return normalized

def scrape_competitor_product(
    db: Session,
    user_id: UUID,
    url: str,
    payload: CompetitorProductCreateScraping,
    *,
    collected_at: datetime | None = None,
) -> ScrapeResult:
    """ Executa scraping de concorrentes de forma síncrona e determinística 
    
    Retorna sempre um :class:`ScrapeResult` alinhado ao contrato consumido
    pelo collector (`success`, `not_modified`, `no_result`, `error`).
    URLs são canônicas antes da coleta para evitar duplicação e permitir
    reaproveitamento de cabeçalhos condicionais.
    """
    normalized_url = _normalize_competitor_scrape_url(str(url))
    normalized_payload = payload.model_copy(update={"product_url": normalized_url})
    existing = _get_existing(db, normalized_payload, normalized_url)
    etag, last_modified = resolve_conditional_headers(existing)

    with ScraperClient() as client:
        response = execute_scraper_fetch(
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
    now = collected_at or datetime.now(timezone.utc)

    if status_code == 304:
        response_result = handle_not_modified_response(
            existing,
            db,
            now=now,
            entity_type="competitor",
        )
        if existing and response_result.persisted_at is not None:
            logger.info(
                "competitor_not_modified",
                product_id=str(existing.id),
                normalized_url=normalized_url,
                last_checked=now.isoformat(),
                collected_at=now.isoformat(),
                persisted_at=response_result.persisted_at.isoformat(),
            )

        return response_result

    if status_code in {400, 403, 422}:
        error_code = response.error_code or "validation_error"
        return ScrapeResult(
            status="error",
            product_id=str(existing.id) if existing else None,
            http_status=status_code,
            error_code=error_code,
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
    availability = metadata.get("availability")
    last_status = metadata.get("last_status")

    availability_flag = bool(availability) if availability is not None else None
    price_value = None
    if payload_model.current_price is not None:
        price_value = ensure_price(payload_model, normalized_url)
        
    resolved_availability = resolve_availability(price_value, availability_flag)
    if resolved_availability is False:
        logger.info(
            "competitor_unavailable_payload",
            url=normalized_url,
            last_status=last_status,
        )

    scraped_info = CompetitorScrapedInfo(
        name=ensure_name(payload_model, normalized_url),
        product_url=normalized_url,
        current_price=price_value,
        old_price=to_decimal(metadata.get("old_price")),
        thumbnail=sanitized_thumbnail,
        free_shipping=bool(metadata.get("free_shipping", False)),
        seller=sanitized_seller,
        seller_rating=to_float(metadata.get("seller_rating")),
        currency=sanitized_currency,
        availability=resolved_availability,
        last_status=last_status,
    )

    competitor = create_or_update_competitor_product_scraped(
        db=db,
        product_data=normalized_payload,
        scraped_info=scraped_info,
        last_checked=now,
        currency=sanitized_currency,
        etag=metadata.etag,
        last_modified=metadata.last_modified,
        collected_at=now,
    )

    persisted_at = datetime.now(timezone.utc)
    if getattr(competitor, "_recompute_comparison", False):
        recompute_reason = getattr(competitor, "_recompute_reason", "material_change")
        request_comparison_recompute(competitor.monitored_product_id, recompute_reason)

    logger.info(
        "competitor_scrape_persisted",
        competitor_id=str(competitor.id),
        monitored_id=str(competitor.monitored_product_id),
        collected_at=now.isoformat(),
        persisted_at=persisted_at.isoformat(),
    )

    return ScrapeResult(
        status="success",
        product_id=str(competitor.id),
        price_changed=bool(getattr(competitor, "_price_changed", True)),
        availability_changed=bool(getattr(competitor, "_availability_changed", True)),
        http_status=200,
        persisted_at=persisted_at,
    )
