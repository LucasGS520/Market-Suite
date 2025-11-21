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
    BulkCompetitorActionRequest,
    BulkCompetitorActionResult,
    CompetitorProductResponse,
    CompetitorScrapeCreationResponse,
    PaginatedCompetitorResponse,
)
from market_alert.services.services_competitors import (
    clear_competitors_from_monitored,
    create_competitor_scrape_request,
    list_competitors_with_pagination,
    pause_competitors_bulk,
    remove_competitors_bulk,
    resume_competitors_bulk,
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
    """ Cria concorrente pendente e agenda scraping para completar informações """
    return create_competitor_scrape_request(
        db=db,
        user=user,
        product_data=product_data,
        request_context={
            "path": request.url.path,
            "method": request.method,
        },
    )

@router.get("/", response_model=PaginatedCompetitorResponse)
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
    
):
    """ Lista concorrentes com os campos mínimos e paginação previsível """
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        monitored_id=str(monitored_product_id),
        page=page,
        per_page=per_page,
    )

    payload = list_competitors_with_pagination(
        db=db,
        user=user,
        monitored_product_id=monitored_product_id,
        page=page,
        per_page=per_page,
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
        total=payload.meta.total,
    )
    return payload

@router.post("/bulk/resume", response_model=BulkCompetitorActionResult)
def resume_competitors(
    request: Request,
    payload: BulkCompetitorActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ Retoma monitoramento dos concorrentes informados """

    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        monitored_id=str(payload.monitored_product_id),
        competitors=len(payload.competitor_ids),
    )

    result = resume_competitors_bulk(
        db=db,
        payload=payload,
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
        processed=result.total_processed,
        skipped=len(result.skipped_ids),
    )

    return result

@router.post("/bulk/pause", response_model=BulkCompetitorActionResult)
def pause_competitors(
    request: Request,
    payload: BulkCompetitorActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ Pausa o monitoramento dos concorrentes informados """

    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        monitored_id=str(payload.monitored_product_id),
        competitors=len(payload.competitor_ids),
    )

    result = pause_competitors_bulk(
        db=db,
        payload=payload,
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
        processed=result.total_processed,
        skipped=len(result.skipped_ids),
    )
    return result

@router.post("/bulk/remove", response_model=BulkCompetitorActionResult)
def remove_competitors(
    request: Request,
    payload: BulkCompetitorActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ Remove definitivamente concorrentes selecionados """

    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        monitored_id=str(payload.monitored_product_id),
        competitors=len(payload.competitor_ids),
    )

    result = remove_competitors_bulk(
        db=db,
        payload=payload,
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
        processed=result.total_processed,
        skipped=len(result.skipped_ids),
    )
    return result

@router.delete("/{monitored_product_id}", response_model=List[CompetitorProductResponse])
def delete_competitors(request: Request, monitored_product_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Remove todos os produtos concorrentes de um produto monitorado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), monitored_id=str(monitored_product_id))

    deleted = clear_competitors_from_monitored(
        db=db,
        monitored_product_id=monitored_product_id,
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
        count=len(deleted)
    )
    return deleted
