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
from market_alert.utils.interval_calculator_products import EVENT_NOT_MODIFIED, calculate_schedule


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
    collected_at: datetime,
) -> ScrapeResult:
    """ Processa reposta do scraper e retorna ``ScrapeResult`` padronizado

    O collector espera sempre um dos status suportados em
    :class:`ScrapeResult`. Este método converte códigos HTTP e payloads do
    scraper no contrato consumido pelas tasks, preservando `http_status`,
    `price_changed` e `availability_changed`. 
    """
    status_code = fetch_result.status_code
    persisted_at: datetime | None = None
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
                #Marca checagem e scraping para evitar lacunas de monitoramento mesmo sem mudanças.
                product.last_checked = last_checked
                product.collected_at = collected_at
                product.status = MonitoredStatus.active
                scheduling = calculate_schedule(
                    product,
                    reference_time=last_checked,
                    event_type=EVENT_NOT_MODIFIED,
                )
                product.stability_score = scheduling.stability_score
                product.next_check_at = scheduling.next_check_at
                db.commit()
                persisted_at = datetime.now(timezone.utc)
                try:
                    #Garante rechecagem assíncrona dos concorrentes sem bloquear a resposta
                    from market_alert.orchestrator.collector_service_orchestrator import enqueue_competitors_for_monitored

                    enqueue_competitors_for_monitored(db, monitored_id=product.id)
                except Exception:
                    logger.exception(
                        "enqueue_competitors_failed",
                        monitored_id=str(product.id),
                    )

                logger.info(
                    "monitored_not_modified",
                    product_id=str(product.id),
                    normalized_url=lookup_url,
                    last_checked=last_checked.isoformat(),
                    collected_at=collected_at.isoformat(),
                    persisted_at=persisted_at.isoformat(),
                )

        return ScrapeResult(
            status="not_modified",
            product_id=str(existing_id) if existing_id else None,
            http_status=304,
            persisted_at=persisted_at,
        )
    
    if status_code in {400, 403, 422}:
        error_code = fetch_result.error_code or "validation_error"
        if error_code == "no_result":
            return ScrapeResult(
                #Evita tratar resposta inválida como ausência legítima de resultado
                status="error",
                product_id=str(existing_id) if existing_id else None,
                http_status=status_code,
                error_code=error_code,
            )
        return ScrapeResult(
            status="error",
            product_id=str(existing_id) if existing_id else None,
            http_status=status_code,
            error_code=error_code,
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
    last_status = metadata.get("last_status")

    availability_flag = bool(availability) if availability is not None else None
    price_value = None
    if payload.current_price is not None and availability_flag is not False:
        price_value = ensure_price(payload, request_url)
    elif availability_flag is False:
        logger.info(
            "monitored_unavailable_payload",
            url=request_url,
            last_status=last_status,
        )

    scraped_info = MonitoredScrapedInfo(
        name=sanitized_name or sanitize_text(monitored_payload.name_identification) or request_url,
        product_url=request_url,
        current_price=price_value,
        thumbnail=sanitized_thumbnail,
        free_shipping=bool(metadata.get("free_shipping", False)),
        currency=sanitized_currency,
        availability=availability_flag,
        last_status=last_status,
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
        collected_at=collected_at,
    )

    price_changed = bool(getattr(product, "_price_changed", True))
    availability_changed = bool(getattr(product, "_availability_changed", True))

    try:
        #Reenfileira concorrentes vinculados após atualizar o monitorado
        from market_alert.orchestrator.collector_service_orchestrator import enqueue_competitors_for_monitored

        enqueue_competitors_for_monitored(db, monitored_id=product.id)
    except Exception:
        logger.exception("enqueue_competitors_failed", monitored_id=str(product.id))
    
    persisted_at = datetime.now(timezone.utc)
    logger.info(
        "monitored_scrape_persisted",
        product_id=str(product.id),
        collected_at=collected_at.isoformat(),
        persisted_at=persisted_at.isoformat(),
    )

    return ScrapeResult(
        status="success",
        product_id=str(product.id),
        price_changed=price_changed,
        availability_changed=availability_changed,
        http_status=200,
        persisted_at=persisted_at,
    )

def scrape_monitored_product(
    db: Session,
    url: str,
    user_id: UUID,
    payload: MonitoredProductCreateScraping,
    *,
    collected_at: datetime | None = None,
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

    now = collected_at or datetime.now(timezone.utc)
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
        collected_at=now,
    )

    return outcome
