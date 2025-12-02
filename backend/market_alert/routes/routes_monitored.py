""" Rotas para produtos monitorados pelo usuário """

import structlog
from fastapi import APIRouter, Depends, Query, Request, status
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
)
from market_alert.core.security import get_current_user
from market_alert.services.services_monitored import (
    delete_monitored_product_entry,
    get_monitored_product,
    list_featured_monitored_products,
    list_monitored_products as list_monitored_products_service,
    schedule_monitored_scrape,
)


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
    per_page: int | None = Query(
        default=None,
        ge=1,
        le=200,
        description="Quantidade de itens por página (máximo 200). Se omitido, retorna todos.",
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
    """ Lista produtos monitorados aplicando filtros textuais e de competitividade.

    Permite omitir `per_page` para entregas completas em fluxos onde a paginação é
    controlada no cliente, mantendo validação de teto quando o parâmetro é usado.
    """
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
    response_payload = list_monitored_products_service(
        db=db,
        user_id=user.id,
        page=page,
        per_page=per_page,
        query=query,
        status=status,
    )

    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        count=len(response_payload.items),
        total=response_payload.meta.total,
        page=page,
        per_page=per_page,
    )
    return response_payload

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
    response_payload = list_featured_monitored_products(
        db=db,
        user_id=user.id,
        limit=MAX_FEATURED_ITEMS,
    )

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
    response_payload = get_monitored_product(
        db=db, product_id=product_id, user_id=user.id
    )
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", product_id=str(product_id))
    return response_payload

@router.delete("/{product_id}", response_model=MonitoredProductResponse)
def delete_product(request: Request, product_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Endpoint para deletar um produto monitorado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), product_id=str(product_id))
    response_payload = delete_monitored_product_entry(
        db=db, product_id=product_id, user_id=user.id
    )
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", product_id=str(product_id))
    return response_payload
