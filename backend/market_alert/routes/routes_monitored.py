""" Rotas para produtos monitorados pelo usuário """

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from uuid import UUID

from shared.infra.db import get_db
from backend.shared.schemas.shared_schemas_products import MonitoredProductCreateScraping

from market_alert.models import User
from market_alert.enums.enums_comparisons import CompetitivenessStatus
from market_alert.schemas.schemas_products import (
    MonitoredProductResponse,
    PaginatedMonitoredProductsResponse,
    MonitoredScrapeCreationResponse,
    PaginationMeta,
)
from market_alert.crud.crud_monitored import (
    get_all_monitored_products,
    get_featured_monitored_products,
    get_monitored_product_by_id,
    delete_monitored_product,
)
from market_alert.crud.crud_comparison import (
    get_latest_summaries_for_products,
    get_latest_summary,
)
from market_alert.core.security import get_current_user
from market_alert.services.services_products import build_monitored_response
from market_alert.services.services_monitored import schedule_monitored_scrape


router = APIRouter(prefix="/monitored", tags=["Monitoramento"])
logger = structlog.get_logger("http_route")

#Limite de itens destacados exibidos simultaneamente no dashboard
MAX_FEATURED_ITEMS = 3

@router.post(
    "/scrape",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MonitoredScrapeCreationResponse,
)
def create_scrape_product(
    request: Request,
    product_data: MonitoredProductCreateScraping,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ Delegação enxuta paara agendar scraping de monitorado """
    return schedule_monitored_scrape(
        db=db,
        user=user,
        product_data=product_data,
        request=request,
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
    query: str | None = Query(
        default=None,
        min_length=1,
        max_length=200,
        description="Busca por nome configurado ou termo do produto",
    ),
    status: CompetitivenessStatus | None = Query(
        default=None,
        description="Filtra pelo status de competitividade mais recente",
    ),
):
    """ Lista produtos monitorados aplicando filtros textuais e de competitividade  """
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        page=page,
        per_page=per_page,
        query=query,
        competitiveness=status.value if status else None,
    )
    products_with_count, total = get_all_monitored_products(
        db,
        user.id,
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
        meta=PaginationMeta(total=total, page=page, per_page=per_page),
    )

@router.get("/featured", response_model=list[MonitoredProductResponse])
def list_featured_products(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ Retorna destaques priorizando variação, alertas ativos e recente adição 
    
    A seleção prioriza: 
    (1) maior variação de preço em 24h, 
    (2) maior número de regras de alerta ativas
    (3) ordem de criação mais recente, garantindo empate consistente sem depender apenas do destaque manual.
    """
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        limit=MAX_FEATURED_ITEMS,
    )
    featured_items = get_featured_monitored_products(
        db,
        user.id,
        limit=MAX_FEATURED_ITEMS,
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

    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        count=len(response_payload),
    )
    return response_payload

@router.get("/{product_id}", response_model=MonitoredProductResponse)
def get_product(request: Request, product_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Endpoint para listar produtos monitorados pelo ID """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), product_id=str(product_id))
    product = get_monitored_product_by_id(db, product_id)
    if not product or product.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", product_id=str(product_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", product_id=str(product_id))
    summary = get_latest_summary(db, product_id)
    return build_monitored_response(product, summary=summary)

@router.delete("/{product_id}", response_model=MonitoredProductResponse)
def delete_product(request: Request, product_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Endpoint para deletar um produto monitorado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), product_id=str(product_id))
    product = get_monitored_product_by_id(db, product_id)
    if not product or product.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", product_id=str(product_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    summary = get_latest_summary(db, product_id)
    response_payload = build_monitored_response(product, summary=summary)
    _ = delete_monitored_product(db, product_id)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", product_id=str(product_id))
    return response_payload
