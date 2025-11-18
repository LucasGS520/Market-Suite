""" Rotas para produtos monitorados pelo usuário """

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from uuid import UUID

from shared.infra.db import get_db
from shared.utils.url_validation import normalize_and_validate_product_url
from backend.shared.schemas.shared_schemas_products import MonitoredProductCreateScraping

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
from market_alert.tasks.scraper_tasks import collect_product_task
from market_alert.core.security import get_current_user
from market_alert.services.services_products import build_monitored_response


router = APIRouter(prefix="/monitored", tags=["Monitoramento"])
logger = structlog.get_logger("http_route")

@router.post("/scrape", status_code=status.HTTP_202_ACCEPTED, response_model=None)
def create_scrape_product(
    request: Request,
    product_data: MonitoredProductCreateScraping,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ Agenda coleta assíncrona de produto monitorado validando URL e duplicidade """
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        monitoring_type="scraping",
    )

    try:
        normalized_url, issue = normalize_and_validate_product_url(str(product_data.product_url))
    except ValueError as exc:
        logger.warning("invalid_product_url", url=str(product_data.product_url), error=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if issue:
        logger.warning("invalid_product_url", url=normalized_url, code=issue.code)
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

    response_payload: list[MonitoredProductResponse] = []
    for product, _ in products_with_count:
            try:
                response_payload.append(build_monitored_response(product))
            except HTTPException as exc:
                #Ignora registros sem preço para manter o contrato enxuto
                logger.warning(
                    "monitored_without_price",
                    product_id=str(product.id),
                    status=product.status.value,
                    detail=str(exc.detail),
                )
                continue

    visible_total = len(response_payload)
    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        count=visible_total,
        total=visible_total,
        page=page,
        per_page=per_page,
    )
    return PaginatedMonitoredProductsResponse(
        items=response_payload,
        total=visible_total,
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
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", product_id=str(product_id))
    return build_monitored_response(product)

@router.delete("/{product_id}", response_model=MonitoredProductResponse)
def delete_product(request: Request, product_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Endpoint para deletar um produto monitorado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), product_id=str(product_id))
    product = get_monitored_product_by_id(db, product_id)
    if not product or product.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", product_id=str(product_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    response_payload = build_monitored_response(product)
    _ = delete_monitored_product(db, product_id)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", product_id=str(product_id))
    return response_payload
