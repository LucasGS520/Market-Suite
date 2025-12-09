""" Serviços de apoio para rotinas de concorrentes monitorados """

from __future__ import annotations

from uuid import UUID
from types import SimpleNamespace
from typing import Callable

import structlog
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.shared.schemas.shared_schemas_products import CompetitorProductCreateScraping
from market_alert.models import User
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.crud.crud_competitor import (
    count_competitors_by_monitored,
    create_pending_competitor_product,
    get_competitor_by_monitored_and_url,
    paginate_competitors,
    delete_competitors_by_monitored_id,
)
from market_alert.schemas.schemas_products import CompetitorScrapeCreationResponse
from market_alert.schemas.schemas_products import (
    PaginationMeta,
    PaginatedCompetitorResponse,
)
from market_alert.services.services_products import build_competitor_response
from market_alert.orchestrator.collector_services import enqueue_competitor_collection
from market_alert.utils.rate_limiter import allow_with_leaky_bucket, parse_rate_limit_config
from market_alert.core.config_alert import settings

from shared.utils.url_validation import normalize_and_validate_product_url
from shared import metrics


logger = structlog.get_logger(__name__)

def ensure_user_can_access_monitored(
    *,
    db: Session,
    product_id: UUID,
    user: User,
    context: dict[str, str] | None = None,
    hide_forbidden: bool = True,
) -> MonitoredProduct:
    """ Valida vínculo do monitorado com o usuário autenticado """
    log_context: dict[str, str] = {"monitored_id": str(product_id)}
    if context:
        log_context.update(context)

    monitored = get_monitored_product_by_id(db, product_id)

    if monitored is None:
        logger.warning("monitored_not_found", **log_context)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto monitorado não encontrado.",
        )

    if monitored.user_id != user.id:
        log_context["owner_id"] = str(monitored.user_id)

        if hide_forbidden:
            #Oculta detalhes para evitar exposição de dados sensíveis
            logger.warning("monitored_forbidden_hidden", **log_context)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Produto monitorado não encontrado.",
            )

        logger.warning("monitored_forbidden", **log_context)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário não possui permissão para acessar este produto monitorado.",
        )

    return monitored

def validate_competitor_limit(
    *,
    db: Session,
    monitored_product_id: UUID,
    limit: int,
    count_competitors_callback,
    context: dict[str, str] | None = None,
) -> None:
    """ Garante que o monitorado respeita o limite máximo de concorrentes """
    log_context = {"monitored_id": str(monitored_product_id), "limit": limit}
    if context:
        log_context.update(context)

    competitors_total = count_competitors_callback(db, monitored_product_id, include_paused=True)

    if competitors_total >= limit:
        logger.warning("competitor_limit_reached", **log_context)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Limite de concorrentes atingido para este produto monitorado.",
        )
    
def enforce_competitor_scrape_rate_limit(user_id: UUID) -> None:
    """Garante que requisições de scraping respeitam limites configurados por usuário."""

    parsed_limit = parse_rate_limit_config(settings.COMPETITOR_RATE_LIMIT)
    if not parsed_limit:
        return

    max_requests, window_seconds = parsed_limit
    bucket_key = f"rate:competitor:{user_id}"

    allowed = allow_with_leaky_bucket(
        bucket_key,
        rate_limit=parsed_limit,
    )

    if not allowed:
        logger.warning(
            "competitor_rate_limit_exceeded",
            user_id=str(user_id),
            limit=max_requests,
            window=window_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de scraping de concorrentes atingido. Tente novamente em instantes.",
        )


def create_competitor_scrape_request(
    *,
    db: Session,
    user: User,
    product_data: CompetitorProductCreateScraping,
    request_context: dict[str, str] | None = None,
) -> CompetitorScrapeCreationResponse:
    """Orquestra validações e agendamento de scraping de concorrente."""

    context = request_context or {}
    log_context = {
        "user_id": str(user.id),
        "monitored_id": str(product_data.monitored_product_id),
        **context,
    }

    logger.info("competitor_scrape_request_received", **log_context)

    try:
        normalized_url, issue = normalize_and_validate_product_url(str(product_data.product_url))
    except ValueError as exc:
        logger.warning("invalid_competitor_url", url=str(product_data.product_url), error=str(exc), **context)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if issue:
        logger.warning("invalid_competitor_url", url=normalized_url, code=issue.code, **context)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=issue.message)

    monitored_product = ensure_user_can_access_monitored(
        db=db,
        product_id=product_data.monitored_product_id,
        user=user,
        context=context,
        hide_forbidden=False,
    )

    existing = get_competitor_by_monitored_and_url(db, monitored_product.id, normalized_url)
    if existing:
        logger.info(
            "competitor_exists",
            monitored_id=str(monitored_product.id),
            competitor_id=str(existing.id),
            **context,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concorrente já cadastrado para este produto monitorado.",
        )

    validate_competitor_limit(
        db=db,
        monitored_product_id=monitored_product.id,
        limit=settings.MAX_COMPETITORS_PER_MONITORED,
        count_competitors_callback=count_competitors_by_monitored,
        context=context,
    )

    enforce_competitor_scrape_rate_limit(user.id)

    pending = create_pending_competitor_product(
        db=db,
        monitored_product_id=monitored_product.id,
        product_url=normalized_url,
        display_name=product_data.name,
    )

    metrics.PENDING_COMPETITOR_CREATED_TOTAL.inc()
    logger.info(
        "pending_competitor_created",
        competitor_id=str(pending.id),
        monitored_id=str(monitored_product.id),
        status=pending.status.value,
        **context,
    )

    #Agendamento via Celery garante processamento assíncrono do scraping
    enqueue_competitor_collection(pending)

    logger.info(
        "competitor_scrape_scheduled",
        competitor_id=str(pending.id),
        monitored_id=str(monitored_product.id),
        **context,
    )

    return CompetitorScrapeCreationResponse(
        id=pending.id,
        url=pending.product_url,
        created_at=pending.created_at,
        message="Scraping de concorrente agendado com sucesso.",
    )

def list_competitors_with_pagination(
    *,
    db: Session,
    user: User,
    monitored_product_id: UUID,
    page: int,
    per_page: int,
    context: dict[str, str] | None = None,
) -> PaginatedCompetitorResponse:
    """ Coordena validação de acesso e paginação simplificada de concorrentes """
    ensure_user_can_access_monitored(
        db=db,
        product_id=monitored_product_id,
        user=user,
        context=context,
        hide_forbidden=False,
    )

    _total, competitors = paginate_competitors(
        db,
        monitored_product_id,
        page=page,
        per_page=per_page,
    )

    items: list = []
    for competitor in competitors:
        try:
            items.append(build_competitor_response(competitor))
        except HTTPException as exc:
            # Ignora concorrentes incompletos preservando previsibilidade da listagem
            logger.warning(
                "competitor_without_price",
                competitor_id=str(competitor.id),
                monitored_id=str(monitored_product_id),
                status=competitor.status.value,
                detail=str(exc.detail),
                **(context or {}),
            )
            continue

    return PaginatedCompetitorResponse(
        items=items,
        meta=PaginationMeta(
            total=len(items),
            page=page,
            per_page=len(items),
        ),
    )

def clear_competitors_from_monitored(
    *,
    db: Session,
    monitored_product_id: UUID,
    user: User,
    context: dict[str, str] | None = None,
) -> list[CompetitorProduct]:
    """ Apaga todos os concorrentes vinculados ao monitorado do usuário """
    ensure_user_can_access_monitored(
        db=db,
        product_id=monitored_product_id,
        user=user,
        context=context,
        hide_forbidden=False,
    )
    
    return delete_competitors_by_monitored_id(db, monitored_product_id)
