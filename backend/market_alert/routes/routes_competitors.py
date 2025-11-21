""" Rotas para gerenciamento de produtos concorrentes monitorados """

from typing import List
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from shared.infra.db import get_db
from backend.shared.schemas.shared_schemas_products import CompetitorProductCreateScraping

from market_alert.models import User
from market_alert.schemas.schemas_products import (
    BulkCompetitorActionRequest,
    BulkCompetitorActionResult,
    CompetitorProductResponse,
    CompetitorScrapeCreationResponse,
    PaginationMeta,
    PaginatedCompetitorResponse,
)
from market_alert.services.services_competitors import (
    create_competitor_scrape_request,
    ensure_user_can_access_monitored,
    load_competitors_for_action,
    validate_competitor_limit,
)
from market_alert.services.services_products import build_competitor_response
from market_alert.crud.crud_competitor import (
    bulk_delete_competitors,
    bulk_update_paused_status,
    count_competitors_by_monitored,
    delete_competitors_by_monitored_id,
    get_competitors_by_monitored_id,
    paginate_competitors,
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

    ensure_user_can_access_monitored(
        db=db,
        product_id=monitored_product_id,
        user=user,
        context={
            "path": request.url.path,
            "method": request.method,
        },
        hide_forbidden=False,
    )

    #Mantemos apenas pafinação essencial para simplificar consumo pelo frontend
    total, competitors = paginate_competitors(
        db,
        monitored_product_id,
        page=page,
        per_page=per_page,
    )

    items: list[CompetitorProductResponse] = []
    for competitor in competitors:
        try:
            items.append(build_competitor_response(competitor))
        except HTTPException as exc:
            #Ignora concorrentes sem preço para manter previsibilidade
            logger.warning(
                "competitor_without_price",
                competitor_id=str(competitor.id),
                monitored_id=str(monitored_product_id),
                status=competitor.status.value,
                detail=str(exc.detail),
            )
            continue
    #Alinha os metadados de paginação aos itens efetivamente retornados após ignorar preços ausentes   
    visible_total = len(items)
    visible_per_page = visible_total
    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        monitored_id=str(monitored_product_id),
        page=page,
        count=visible_total,
        total=total,
    )

    #Retornamos paginação coerente com a quantidade realmente exibida ao consumidor
    return PaginatedCompetitorResponse(
        items=items,
        meta=PaginationMeta(
            total=visible_total,
            page=page,
            per_page=visible_per_page,
        )
    )

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

    ensure_user_can_access_monitored(
        db=db,
        product_id=payload.monitored_product_id,
        user=user,
        context={
            "path": request.url.path,
            "method": request.method,
        },
        hide_forbidden=False,
    )

    competitors = load_competitors_for_action(
        db=db,
        monitored_product_id=payload.monitored_product_id,
        competitor_ids=payload.competitor_ids,
    )

    updated = bulk_update_paused_status(db, competitors, paused=False)
    processed_ids = [item.id for item in updated]
    skipped = [cid for cid in payload.competitor_ids if cid not in processed_ids]

    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        processed=len(processed_ids),
        skipped=len(skipped),
    )

    return BulkCompetitorActionResult(
        processed_ids=processed_ids,
        skipped_ids=skipped,
        total_processed=len(processed_ids),
    )

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

    ensure_user_can_access_monitored(
        db=db,
        product_id=payload.monitored_product_id,
        user=user,
        context={
            "path": request.url.path,
            "method": request.method,
        },
        hide_forbidden=False,
    )

    competitors = load_competitors_for_action(
        db=db,
        monitored_product_id=payload.monitored_product_id,
        competitor_ids=payload.competitor_ids,
    )

    # Reutiliza a função de atualização em massa para marcar os concorrentes como pausados
    updated = bulk_update_paused_status(db, competitors, paused=True)
    processed_ids = [item.id for item in updated]
    skipped = [cid for cid in payload.competitor_ids if cid not in processed_ids]

    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        processed=len(processed_ids),
        skipped=len(skipped),
    )

    return BulkCompetitorActionResult(
        processed_ids=processed_ids,
        skipped_ids=skipped,
        total_processed=len(processed_ids),
    )

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

    ensure_user_can_access_monitored(
        db=db,
        product_id=payload.monitored_product_id,
        user=user,
        context={
            "path": request.url.path,
            "method": request.method,
        },
        hide_forbidden=False,
    )

    competitors = load_competitors_for_action(
        db=db,
        monitored_product_id=payload.monitored_product_id,
        competitor_ids=payload.competitor_ids,
    )

    removed = bulk_delete_competitors(db, competitors)
    processed_ids = [item.id for item in competitors]
    skipped = [cid for cid in payload.competitor_ids if cid not in processed_ids]

    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        processed=removed,
        skipped=len(skipped),
    )

    return BulkCompetitorActionResult(
        processed_ids=processed_ids,
        skipped_ids=skipped,
        total_processed=removed,
    )

@router.delete("/{monitored_product_id}", response_model=List[CompetitorProductResponse])
def delete_competitors(request: Request, monitored_product_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Remove todos os produtos concorrentes de um produto monitorado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), monitored_id=str(monitored_product_id))

    ensure_user_can_access_monitored(
        db=db,
        product_id=monitored_product_id,
        user=user,
        context={
            "path": request.url.path,
            "method": request.method,
        },
        hide_forbidden=False,
    )

    deleted = delete_competitors_by_monitored_id(db, monitored_product_id)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", count=len(deleted))
    return deleted
