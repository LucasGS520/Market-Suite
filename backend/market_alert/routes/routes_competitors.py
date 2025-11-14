""" Rotas para gerenciamento de produtos concorrentes monitorados """

from typing import List
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from shared.infra.db import get_db
from backend.shared.schemas.shared_schemas_products import CompetitorProductCreateScraping

from market_alert.models import User
from market_alert.schemas.schemas_products import (
    BulkCompetitorActionRequest,
    BulkCompetitorActionResult,
    CompetitorProductResponse,
    PaginatedCompetitorResponse,
)
from market_alert.services.services_competitors import (
    ensure_user_can_access_monitored,
    load_competitors_for_action,
    map_competitor_to_response,
    validate_competitor_limit,
)
from market_alert.enums.enums_products import ProductStatus
from market_alert.crud.crud_competitor import (
    bulk_delete_competitors,
    bulk_update_paused_status,
    count_competitors_by_monitored,
    delete_competitors_by_monitored_id,
    get_competitor_by_monitored_and_url,
    get_competitors_by_monitored_id,
    paginate_competitors,
)
from market_alert.tasks.scraper_tasks import collect_competitor_task
from market_alert.core.security import get_current_user
from market_alert.core.config_alert import settings

from shared.utils.url_validation import normalize_and_validate_product_url


router = APIRouter(prefix="/competitors", tags=["Concorrentes"])
logger = structlog.get_logger("http_route")

ALLOWED_SORT_FIELDS = {"price", "last_checked", "price_change"}
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


@router.post("/scrape", status_code=status.HTTP_202_ACCEPTED, response_model=None)
def create_competitor_scrape(request: Request, product_data: CompetitorProductCreateScraping, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    def create_competitor_scrape(
    request: Request,
    product_data: CompetitorProductCreateScraping,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """ Endpoint para monitorar e comparar um produto concorrente por meio de um link direto (scraping)

    O header ``Idempotency-Key`` é aceito para que clientes previnam agendamentos duplicados
    em fluxos de scraping.
    """
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        monitored_id=str(product_data.monitored_product_id),
        idempotency_key=idempotency_key,
    )

    try:
        normalized_url, issue = normalize_and_validate_product_url(str(product_data.product_url))
    except ValueError as exc:
        logger.warning("invalid_competitor_url", url=str(product_data.product_url), error=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if issue:
        logger.warning("invalid_competitor_url", url=normalized_url, code=issue.code)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=issue.message)

    mp = ensure_user_can_access_monitored(
        db=db,
        product_id=product_data.monitored_product_id,
        user=user,
        context={
            "path": request.url.path,
            "method": request.method,
        },
        hide_forbidden=False,
    )

    #Checa duplicidade com base na URL canônica
    existing = get_competitor_by_monitored_and_url(db, mp.id, normalized_url)
    if existing:
        logger.info(
            "competitor_existis",
            path=request.url.path,
            method=request.method,
            monitored_id=str(mp.id),
            competitor_id=str(existing.id),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concorrente já cadastrado para este produto monitorado.",
        )
    
    validate_competitor_limit(
        db=db,
        monitored_product_id=mp.id,
        limit=settings.MAX_COMPETITORS_PER_MONITORED,
        count_competitors_callback=count_competitors_by_monitored,
        context={
            "path": request.url.path,
            "method": request.method,
        },
    )

    #Cria um produto concorrente via Celery
    collect_competitor_task.delay(
        monitored_product_id=str(product_data.monitored_product_id),
        url=normalized_url,
    )

    logger.info("route_completed", path=request.url.path, method=request.method, status="scheduled")
    return {"message": "Scraping de concorrente agendado com sucesso."}

@router.get("/", response_model=PaginatedCompetitorResponse)
def list_competitors(
    request: Request,
    *,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    monitored_product_id: UUID = Query(..., alias="monitored_id"),
    page: int = Query(1, ge=1),
    per_page: int = Query(DEFAULT_PER_PAGE, ge=1, le=MAX_PER_PAGE),
    search: str | None = Query(None, max_length=120),
    status: ProductStatus | None = Query(None),
    include_paused: bool = Query(True),
    sort_by: str = Query("last_checked"),
    sort_direction: str = Query("desc"),
):
    """ Lista concorrentes com filtros, ordenação e paginação """
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
    )

    normalized_sort = (sort_by or "last_checked").lower()
    if normalized_sort not in ALLOWED_SORT_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Campo de ordenação inválido.",
        )

    normalized_direction = (sort_direction or "desc").lower()
    if normalized_direction not in {"asc", "desc"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Direção de ordenação inválida.",
        )

    total, competitors = paginate_competitors(
        db,
        monitored_product_id,
        page=page,
        per_page=per_page,
        search=search,
        status=status,
        include_paused=include_paused,
        sort_by=normalized_sort,
        sort_direction=normalized_direction,
    )

    items = [map_competitor_to_response(item) for item in competitors]
    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        monitored_id=str(monitored_product_id),
        page=page,
        count=len(items),
        total=total,
    )

    return PaginatedCompetitorResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
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
    )

    deleted = delete_competitors_by_monitored_id(db, monitored_product_id)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", count=len(deleted))
    return deleted
