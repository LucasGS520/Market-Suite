""" Rotas para gerenciamento de produtos concorrentes monitorados """

from typing import List
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from shared.infra.db import get_db
from backend.shared.schemas.shared_schemas_products import CompetitorProductCreateScraping

from market_alert.models import User
from market_alert.schemas.schemas_products import (
    CompetitorScrapeCreationResponse,
    CompetitorsListResponse,
)
from market_alert.services.services_competitors import list_competitors_with_pagination
from market_alert.services.services_competitor_lifecycle import (
    clear_competitors_from_monitored,
    create_competitor_scrape_request,
    delete_competitor_entry,
)
from market_alert.core.security import get_current_user


router = APIRouter(prefix="/competitors", tags=["Concorrentes"])
logger = structlog.get_logger("http_route")

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100

@router.post(
    "/scrape",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CompetitorScrapeCreationResponse,
)
def create_competitor_scrape(
    request: Request,
    product_data: CompetitorProductCreateScraping,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ Cria concorrente pendente e garante monitorado na fila de prioridade """
    return create_competitor_scrape_request(
        db=db,
        user=user,
        product_data=product_data,
        request_context={
            "path": request.url.path,
            "method": request.method,
        },
    )

@router.get("/", response_model=CompetitorsListResponse)
def list_competitors(
    request: Request,
    *,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    monitored_product_id: UUID = Query(..., alias="monitored_id"),
    page: int = Query(
        1,
        ge=1,
        description="Página atual da listagem de concorrentes (base 1)",
    ),
    per_page: int = Query(
        DEFAULT_PER_PAGE,
        ge=1,
        le=MAX_PER_PAGE,
        description="Quantidade de concorrentes retornados por página",
    ),
    include_inactive: bool = Query(
        True,
        description="Inclui concorrentes indisponíveis ou sem preço na listagem",
    ),
    include_paused: bool = Query(
        True,
        description="Inclui concorrentes pausados sem impactar contadores de preço",
    ),
    
):
    """ Lista concorrentes sem filtrar inativos, preservando contagens úteis """
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        monitored_id=str(monitored_product_id),
        page=page,
        per_page=per_page,
        include_inactive=include_inactive,
        include_paused=include_paused,
    )

    payload = list_competitors_with_pagination(
        db=db,
        user=user,
        monitored_product_id=monitored_product_id,
        page=page,
        per_page=per_page,
        include_inactive=include_inactive,
        include_paused=include_paused,
        context={
            "path": request.url.path,
            "method": request.method,
        },
    )

    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        monitored_id=str(monitored_product_id),
        page=page,
        count=len(payload.items),
        total=payload.competitors_total,
    )
    return payload

@router.delete("/{competitor_id}", status_code=status.HTTP_200_OK)
def delete_competitor(
    request: Request,
    competitor_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ Remove um concorrente específico e aciona recálculo do monitorado """
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        competitor_id=str(competitor_id),
    )

    delete_competitor_entry(
        db=db,
        competitor_id=competitor_id,
        user=user,
        context={
            "path": request.url.path,
            "method": request.method,
        },
    )

    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        competitor_id=str(competitor_id),

    )
    return {"success": True, "competitor_id": str(competitor_id)}
