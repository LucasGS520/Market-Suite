""" Camada de serviço para criação, listagem e agendar monitorados """

from __future__ import annotations

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session
import structlog
from uuid import UUID

from backend.shared.schemas.shared_schemas_products import MonitoredProductCreateScraping
from shared.utils.url_validation import normalize_and_validate_product_url

from market_alert.core.config_alert import settings
from market_alert.crud.crud_monitored import (
    create_pending_monitored_product,
    get_monitored_product_by_user_and_url,
    get_all_monitored_products,
    get_featured_monitored_products,
    get_monitored_product_by_id,
    delete_monitored_product,
)
from market_alert.crud.crud_comparison import (
    get_latest_summaries_for_products,
    get_latest_summary,
)
from market_alert.models import User
from market_alert.schemas.schemas_products import (
    MonitoredProductResponse,
    MonitoredScrapeCreationResponse,
    PaginatedMonitoredProductsResponse,
    PaginationMeta,
)
from market_alert.enums.enums_comparisons import CompetitivenessStatus
from market_alert.services.services_products import build_monitored_response
from market_alert.tasks.scraper_tasks import collect_product_task
from market_alert.utils.rate_limiter import allow_with_leaky_bucket, parse_rate_limit_config


logger = structlog.get_logger("monitored_service")

def list_monitored_products(
    *,
    db: Session,
    user_id: UUID,
    page: int,
    per_page: int,
    query: str | None = None,
    status: CompetitivenessStatus | None = None,
) -> PaginatedMonitoredProductsResponse:
    """ Agrupa monitorados em resposta paginada com resumos calculados.

    A função mantém a lógica de obtenção de resumos mais recentes e montagem
    do DTO de monitorados, filtrando itens sem preço para preservar o contrato.
    """
    products_with_count, total = get_all_monitored_products(
        db,
        user_id,
        page=page,
        per_page=per_page,
        query=query,
        status=status,
    )

    product_ids = [product.id for product, _ in products_with_count]
    summaries_map = get_latest_summaries_for_products(db, product_ids)

    response_payload: list[MonitoredProductResponse] = []
    for product, _ in products_with_count:
        try:
            response_payload.append(
                build_monitored_response(
                    product, summary=summaries_map.get(product.id)
                )
            )
        except HTTPException as exc:
            #Ignora registros sem preço para manter o contrato enxuto
            logger.warning(
                "monitored_without_price",
                product_id=str(product.id),
                status=product.status.value,
                detail=str(exc.detail),
            )
            continue

    return PaginatedMonitoredProductsResponse(
        items=response_payload,
        meta=PaginationMeta(total=total, page=page, per_page=per_page),
    )


def list_featured_monitored_products(
    *, db: Session, user_id: UUID, limit: int
) -> list[MonitoredProductResponse]:
    """ Seleciona destaques e monta contratos prontos para a rota.

    A função centraliza a obtenção dos resumos e aplica o mesmo tratamento de
    itens sem preço para evitar respostas inconsistentes.
    """
    featured_items = get_featured_monitored_products(
        db,
        user_id,
        limit=limit,
    )

    summary_map = get_latest_summaries_for_products(
        db, [product.id for product in featured_items]
    )

    response_payload: list[MonitoredProductResponse] = []
    for product in featured_items:
        try:
            response_payload.append(
                build_monitored_response(
                    product, summary=summary_map.get(product.id)
                )
            )
        except HTTPException as exc:
            #Manter o contrato consistente mesmo que algum destaque esteja sem preço
            logger.warning(
                "featured_without_price",
                product_id=str(product.id),
                status=product.status.value,
                detail=str(exc.detail),
            )
            continue

    return response_payload


def get_monitored_product(
    *, db: Session, product_id: UUID, user_id: UUID
) -> MonitoredProductResponse:
    """ Recupera monitorado por ID, garantindo posse e contrato consolidado """
    product = get_monitored_product_by_id(db, product_id)
    if not product or product.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado.",
        )

    summary = get_latest_summary(db, product_id)
    return build_monitored_response(product, summary=summary)


def delete_monitored_product_entry(
    *, db: Session, product_id: UUID, user_id: UUID
) -> MonitoredProductResponse:
    """ Remove monitorado após validar posse e monta resposta final.

    Centraliza a busca do resumo para devolver o contrato esperado mesmo após a
    exclusão do registro principal.
    """
    product = get_monitored_product_by_id(db, product_id)
    if not product or product.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado.",
        )

    summary = get_latest_summary(db, product_id)
    response_payload = build_monitored_response(product, summary=summary)
    _ = delete_monitored_product(db, product_id)
    return response_payload

def schedule_monitored_scrape(
    *,
    db: Session,
    user: User,
    product_data: MonitoredProductCreateScraping,
    request: Request | None = None,
) -> MonitoredScrapeCreationResponse:
    """ Valida e agenda scraping de produto monitorado em fluxo único
    
    O serviço centraliza logs e validações para reduzir duplicação entre rotas,
    garantindo verificação de URL, duplicidade e rate-limit antes de agendar a
    coleta assíncrona.
    """
    log_context: dict[str, str | None] = {
        "user_id": str(user.id),
        "path": request.url.path if request else None,
        "method": request.method if request else None,
        "monitoring_type": "scraping",
    }
    logger.info(
        "monitored_scrape_requested",
        **{key: value for key, value in log_context.items() if value is not None},
    )

    try:
        normalized_url, issue = normalize_and_validate_product_url(
            str(product_data.product_url)
        )
    except ValueError as exc:
        logger.warning(
            "monitored_invalid_url", url=str(product_data.product_url), error=str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if issue:
        logger.warning("monitored_invalid_url", url=normalized_url, code=issue.code)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=issue.message
        )
    
    existing = get_monitored_product_by_user_and_url(db, user.id, normalized_url)

    if existing:
        if (
            product_data.name_identification
            and existing.name_identification != product_data.name_identification
        ):
            #Atualiza a identificação para refletir a escolha mais recente do usuário
            existing.name_identification = product_data.name_identification
            db.commit()
            db.refresh(existing)

        logger.info("monitored_already_exists", monitored_id=str(existing.id))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este produto já está sendo monitorado.",
        )
    
    parsed_limit = parse_rate_limit_config(settings.SCRAPER_RATE_LIMIT)
    if parsed_limit:
        max_requests, window_seconds = parsed_limit
        bucket_key = f"rate:scrape:{user.id}"
        allowed = allow_with_leaky_bucket(
            bucket_key,
            rate_limit=parsed_limit,
        )

        if not allowed:
            logger.warning(
                "monitored_rate_limit_exceeded",
                user_id=str(user.id),
                limit=max_requests,
                window=window_seconds,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Limite de scraping atingido. Tente novamente em instantes.",
            )

    pending = create_pending_monitored_product(
        db=db,
        user_id=user.id,
        name_identification=product_data.name_identification,
        product_url=normalized_url,
    )

    collect_product_task.delay(
        url=normalized_url,
        user_id=str(user.id),
        name_identification=pending.name_identification,
        monitored_id=str(pending.id),
    )

    logger.info(
        "monitored_scrape_scheduled", monitored_id=str(pending.id), url=normalized_url
    )

    return MonitoredScrapeCreationResponse(
        id=pending.id,
        url=pending.normalized_url,
        created_at=pending.created_at,
        message="Scraping agendado. O produto será salvo em breve.",
    )
