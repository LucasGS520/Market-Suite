""" Rotas para gerenciamento de produtos concorrentes monitorados """

from typing import Iterable, List
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from shared.infra.db import get_db
from backend.shared.schemas.shared_schemas_products import CompetitorProductCreateScraping

from market_alert.models import User
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.schemas.schemas_products import (
    BulkCompetitorActionRequest,
    BulkCompetitorActionResult,
    CompetitorListItemResponse,
    CompetitorProductResponse,
    PaginatedCompetitorResponse,
)
from market_alert.enums.enums_products import ProductStatus
from market_alert.crud.crud_monitored import get_monitored_product_by_id
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


def _to_decimal_str(value) -> str | None:
    """ Converte valores numéricos/Decimal em string para JSON """

    if value is None:
        return None
    return str(value)


def _calculate_price_change(competitor: CompetitorProduct) -> tuple[str | None, str | None]:
    """ Calcula variação absoluta e percentual entre preço atual e anterior """

    current = competitor.current_price
    previous = competitor.old_price
    if current is None or previous is None:
        return None, None

    absolute_change = current - previous
    try:
        percentage_change = (absolute_change / previous) * 100 if previous else None
    except ZeroDivisionError:
        percentage_change = None

    absolute_str = _to_decimal_str(absolute_change)
    percentage_str = None
    if percentage_change is not None:
        percentage_str = f"{percentage_change:.4f}"

    return absolute_str, percentage_str


def _map_competitor_to_response(competitor: CompetitorProduct) -> CompetitorListItemResponse:
    """ Normaliza modelo ORM para estrutura enxuta de listagem """

    absolute_change, percentage_change = _calculate_price_change(competitor)
    return CompetitorListItemResponse(
        id=competitor.id,
        monitored_product_id=competitor.monitored_product_id,
        name=competitor.name_competitor,
        product_url=competitor.product_url,
        current_price=_to_decimal_str(competitor.current_price),
        previous_price=_to_decimal_str(competitor.old_price),
        price_change=absolute_change,
        price_change_percentage=percentage_change,
        status=competitor.status,
        last_checked=competitor.last_checked,
        is_paused=competitor.is_paused,
    )


def _ensure_user_owns_product(
    *,
    db: Session,
    product_id: UUID,
    user: User,
    request: Request,
) -> MonitoredProduct:
    """ Valida se monitorado pertence ao usuário autenticado """

    monitored = get_monitored_product_by_id(db, product_id)
    if monitored is None or monitored.user_id != user.id:
        logger.warning(
            "route_error",
            path=request.url.path,
            method=request.method,
            reason="not_found",
            monitored_id=str(product_id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto monitorado não encontrado.",
        )
    return monitored


def _load_competitors_for_action(
    db: Session,
    monitored_product_id: UUID,
    competitor_ids: Iterable[UUID],
) -> List[CompetitorProduct]:
    """ Recupera concorrentes específicos garantindo vínculo com o monitorado """

    unique_ids = {UUID(str(item)) for item in competitor_ids}
    if not unique_ids:
        return []

    return (
        db.query(CompetitorProduct)
        .filter(
            CompetitorProduct.monitored_product_id == monitored_product_id,
            CompetitorProduct.id.in_(unique_ids),
        )
        .all()
    )

@router.post("/scrape", status_code=status.HTTP_202_ACCEPTED, response_model=None)
def create_competitor_scrape(request: Request, product_data: CompetitorProductCreateScraping, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Endpoint para monitorar e comparar um produto concorrente por meio de um link direto (scraping) """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), monitored_id=str(product_data.monitored_product_id))

    try:
        normalized_url, issue = normalize_and_validate_product_url(str(product_data.product_url))
    except ValueError as exc:
        logger.warning("invalid_competitor_url", url=str(product_data.product_url), error=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if issue:
        logger.warning("invalid_competitor_url", url=normalized_url, code=issue.code)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=issue.message)

    #Valida se o produto monitorado existe e pertence ao usuário antes de agendar scraping
    mp = get_monitored_product_by_id(db, product_data.monitored_product_id)
    if mp is None:
        logger.warning(
            "route_error",
            path=request.url.path,
            method=request.method,
            reason="not_found",
            monitored_id=str(product_data.monitored_product_id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto monitorado não encontrado.",
        )
    
    if mp.user_id != user.id:
        logger.warning(
            "route_error",
            path=request.url.path,
            method=request.method,
            reason="forbidden",
            monitored_id=str(product_data.monitored_product_id),
            owner_id=str(mp.user_id),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário não possui permissão para acessar este produto monitorado.",
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
    
    competitors_total = count_competitors_by_monitored(db, mp.id, include_paused=True)
    if competitors_total >= settings.MAX_COMPETITORS_PER_MONITORED:
        logger.warning(
            "competitor_limit_reached",
            path=request.url.path,
            method=request.method,
            monitored_id=str(mp.id),
            limit=settings.MAX_COMPETITORS_PER_MONITORED,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Limite de concorrentes atingido para este produto monitorado.",
        )

    #Cria um produto concorrente via Celery
    collect_competitor_task.delay(
        monitored_product_id=str(product_data.monitored_product_id),
        url=normalized_url
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

    _ensure_user_owns_product(
        db=db,
        product_id=monitored_product_id,
        user=user,
        request=request,
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

    items = [_map_competitor_to_response(item) for item in competitors]
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

    _ensure_user_owns_product(
        db=db,
        product_id=payload.monitored_product_id,
        user=user,
        request=request,
    )

    competitors = _load_competitors_for_action(
        db,
        payload.monitored_product_id,
        payload.competitor_ids,
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

    _ensure_user_owns_product(
        db=db,
        product_id=payload.monitored_product_id,
        user=user,
        request=request,
    )

    competitors = _load_competitors_for_action(
        db,
        payload.monitored_product_id,
        payload.competitor_ids,
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

    #Valida produto monitorado pertence ao usuário
    mp = get_monitored_product_by_id(db, monitored_product_id)
    if not mp or mp.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", monitored_id=str(monitored_product_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto monitorado não encontrado.")

    deleted = delete_competitors_by_monitored_id(db, monitored_product_id)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", count=len(deleted))
    return deleted
