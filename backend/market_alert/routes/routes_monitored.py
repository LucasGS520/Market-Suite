""" Rotas para produtos monitorados pelo usuário """

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from uuid import UUID

from shared.infra.db import get_db
from shared.utils.url_validation import normalize_and_validate_product_url
from backend.shared.schemas.shared_schemas_products import MonitoredProductCreateScraping
from backend.shared.infra.redis import (
    IdempotencyOwnershipError,
    register_idempotency_key,
    store_idempotency_response,
)
from market_alert.core.config_alert import settings

from market_alert.models import User
from market_alert.schemas.schemas_products import (
    MonitoredProductResponse,
    PaginatedMonitoredProductsResponse,
)
from market_alert.crud.crud_monitored import (
    get_all_monitored_products,
    get_monitored_product_by_id,
    delete_monitored_product,
    create_pending_monitored_product,
    get_monitored_product_by_user_and_url,
)
from market_alert.crud.crud_comparison import (
    get_latest_comparisons_for_products,
    get_latest_summaries_for_products,
)
from market_alert.tasks.scraper_tasks import collect_product_task
from market_alert.core.security import get_current_user
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.services.services_comparison import build_comparison_summary


router = APIRouter(prefix="/monitored", tags=["Monitoramento"])
logger = structlog.get_logger("http_route")

@router.post("/scrape", status_code=status.HTTP_202_ACCEPTED, response_model=None)
def create_scrape_product(
    request: Request,
    product_data: MonitoredProductCreateScraping,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """ Agenda coleta assíncrona de produto monitorado validando URL e duplicidade """
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        monitoring_type="scraping",
        idempotency_key=idempotency_key,
    )

    owner_reference = str(user.id)
    idempotency_record = None

    try:
        idempotency_record = register_idempotency_key(
            namespace="monitored_scrape",
            key=idempotency_key,
            owner=owner_reference,
            ttl_seconds=settings.IDEMPOTENCY_TTL_SECONDS,
        )
    except IdempotencyOwnershipError as exc:
        logger.warning("idempotency_conflict", path=request.url.path, method=request.method, key=idempotency_key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chave de idempotência já utilizada por outro usuário",
        ) from exc

    if idempotency_record and not idempotency_record.is_new:
        logger.info("idempotency_replayed", path=request.url.path, method=request.method, key=idempotency_key)
        if idempotency_record.response is not None:
            return JSONResponse(
                content=idempotency_record.response,
                status_code=idempotency_record.status_code or status.HTTP_202_ACCEPTED,
            )
        return JSONResponse(
            content={"message": "Requisição já processada anteriormente."},
            status_code=status.HTTP_202_ACCEPTED,
        )

    try:
        normalized_url, issue = normalize_and_validate_product_url(str(product_data.product_url))
    except ValueError as exc:
        logger.warning("invalid_product_url", url=str(product_data.product_url), error=str(exc))
        error_payload = {"detail": str(exc)}
        if idempotency_record:
            store_idempotency_response(
                namespace="monitored_scrape",
                key=idempotency_key,
                owner=owner_reference,
                ttl_seconds=settings.IDEMPOTENCY_TTL_SECONDS,
                response=error_payload,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if issue:
        logger.warning("invalid_product_url", url=normalized_url, code=issue.code)
        error_payload = {"detail": issue.message}
        if idempotency_record:
            store_idempotency_response(
                namespace="monitored_scrape",
                key=idempotency_key,
                owner=owner_reference,
                ttl_seconds=settings.IDEMPOTENCY_TTL_SECONDS,
                response=error_payload,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=issue.message)

    existing = get_monitored_product_by_user_and_url(db, user.id, normalized_url)

    if existing:
        logger.info(
            "scrape_skipped_existing",
            path=request.url.path,
            method=request.method,
            status="already_monitored",
            monitored_id=str(existing.id),
        )
        if (
            product_data.name_identification
            and existing.name_identification != product_data.name_identification
        ):
            #Atualiza a identificação quando o usuário ajusta o nome manualmente
            existing.name_identification = product_data.name_identification
            db.commit()
            db.refresh(existing)

        conflict_payload = {"message": "Este produto já está sendo monitorado."}
        if idempotency_record:
            store_idempotency_response(
                namespace="monitored_scrape",
                key=idempotency_key,
                owner=owner_reference,
                ttl_seconds=settings.IDEMPOTENCY_TTL_SECONDS,
                response=conflict_payload,
                status_code=status.HTTP_409_CONFLICT,
            )

        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=conflict_payload,
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

    logger.info("route_completed", path=request.url.path, method=request.method, status="scheduled", monitored_id=str(pending.id))
    response_payload = {"message": "Scraping agendado. O produto será salvo em breve."}

    if idempotency_record:
        store_idempotency_response(
            namespace="monitored_scrape",
            key=idempotency_key,
            owner=owner_reference,
            ttl_seconds=settings.IDEMPOTENCY_TTL_SECONDS,
            response=response_payload,
            status_code=status.HTTP_202_ACCEPTED,
        )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=response_payload,
    )

@router.get("/", response_model=PaginatedMonitoredProductsResponse)
def list_monitored_products(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Página atual (base 1)"),
    per_page: int = Query(
        50,
        ge=1,
        le=200,
        description="Quantidade de itens por página (máximo 200)",
    ),
):
    """ Endpoint para listar produtos monitorados com suporte a paginação """
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        page=page,
        per_page=per_page,
    )
    products_with_count, total = get_all_monitored_products(
        db,
        user.id,
        page=page,
        per_page=per_page,
    )

    product_ids = [product.id for product, _ in products_with_count]

    if not product_ids:
        logger.info(
            "route_completed",
            path=request.url.path,
            method=request.method,
            status="success",
            count=0,
            total=total,
            page=page,
            per_page=per_page,
        )
        return PaginatedMonitoredProductsResponse(
            items=[],
            total=total,
            page=page,
            per_page=per_page,
        )
    
    latest_comparisons = get_latest_comparisons_for_products(db, product_ids)
    latest_summaries = get_latest_summaries_for_products(db, product_ids)

    response_payload: list[MonitoredProductResponse] = []
    for product, competitors_count in products_with_count:
        comparison = latest_comparisons.get(product.id)
        summary = build_comparison_summary(
            comparison,
            competitors_count=competitors_count,
            stored_summary=latest_summaries.get(product.id),
        )
        is_new = product.status == MonitoredStatus.pending or summary["last_comparison_at"] is None

        #Propaga campos agregados para o contrato exposto ao frontend
        response_payload.append(
            MonitoredProductResponse.model_validate(product).model_copy(
                update={
                    "competitors_count": competitors_count,
                    "competitors_mean": summary["competitors_mean"],
                    "competitors_min": summary["competitors_min"],
                    "competitors_max": summary["competitors_max"],
                    "position_rank": summary["position_rank"],
                    "potential_savings": summary["potential_savings"],
                    "competitors_with_price_count": summary["competitors_with_price_count"],
                    "latest_comparison_id": summary["comparison_id"],
                    "last_comparison_at": summary["last_comparison_at"],
                    "is_new": is_new,
                    "comparison_insights": summary["comparison_insights"],
                }
            )
        )

    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        count=len(response_payload),
        total=total,
        page=page,
        per_page=per_page,
    )
    return PaginatedMonitoredProductsResponse(
        items=response_payload,
        total=total,
        page=page,
        per_page=per_page,
    )

@router.get("/{product_id}", response_model=MonitoredProductResponse)
def get_product(request: Request, product_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Endpoint para listar produtos monitorados pelo ID """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), product_id=str(product_id))
    product = get_monitored_product_by_id(db, product_id)
    if not product or product.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", product_id=str(product_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    latest_comparison = get_latest_comparisons_for_products(db, [product.id]).get(product.id)
    latest_summary = get_latest_summaries_for_products(db, [product.id]).get(product.id)
    competitors_count = len(getattr(product, "competitors", []) or [])
    summary = build_comparison_summary(
        latest_comparison,
        competitors_count=competitors_count,
        stored_summary=latest_summary,
    )
    is_new = product.status == MonitoredStatus.pending or summary["last_comparison_at"] is None
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", product_id=str(product_id))
    return MonitoredProductResponse.model_validate(product).model_copy(
        update={
            "competitors_count": competitors_count,
            "competitors_mean": summary["competitors_mean"],
            "competitors_min": summary["competitors_min"],
            "competitors_max": summary["competitors_max"],
            "position_rank": summary["position_rank"],
            "potential_savings": summary["potential_savings"],
            "competitors_with_price_count": summary["competitors_with_price_count"],
            "latest_comparison_id": summary["comparison_id"],
            "last_comparison_at": summary["last_comparison_at"],
            "is_new": is_new,
            "comparison_insights": summary["comparison_insights"],
        }
    )

@router.delete("/{product_id}", response_model=MonitoredProductResponse)
def delete_product(request: Request, product_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Endpoint para deletar um produto monitorado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), product_id=str(product_id))
    product = get_monitored_product_by_id(db, product_id)
    if not product or product.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", product_id=str(product_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    deleted = delete_monitored_product(db, product_id)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", product_id=str(product_id))
    return deleted
