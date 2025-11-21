""" Rotas para gerenciamento de produtos concorrentes monitorados """

from typing import List, Tuple
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from shared.infra.db import get_db
from backend.shared.schemas.shared_schemas_products import CompetitorProductCreateScraping
from shared.utils.redis_client import consume_leaky_bucket

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
    ensure_user_can_access_monitored,
    load_competitors_for_action,
    validate_competitor_limit,
)
from market_alert.services.services_products import build_competitor_response
from market_alert.crud.crud_competitor import (
    bulk_delete_competitors,
    bulk_update_paused_status,
    count_competitors_by_monitored,
    create_pending_competitor_product,
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

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100

def _parse_rate_limit_config(rate_limit: str) -> Tuple[int, int] | None:
    """Converte configuração ``valor/unidade`` em tupla ``(valor, janela_em_segundos)``."""

    cleaned = (rate_limit or "").strip()
    if not cleaned or "/" not in cleaned:
        return None

    amount_part, window_part = cleaned.split("/", 1)
    try:
        max_requests = int(amount_part)
    except ValueError:
        logger.warning("invalid_rate_limit_config", raw=rate_limit)
        return None

    unit = window_part.strip().lower()
    unit_mapping = {
        "s": 1,
        "sec": 1,
        "secs": 1,
        "second": 1,
        "seconds": 1,
        "m": 60,
        "min": 60,
        "mins": 60,
        "minute": 60,
        "minutes": 60,
        "h": 3600,
        "hour": 3600,
        "hours": 3600,
    }

    if unit.isdigit():
        window_seconds = int(unit)
    else:
        window_seconds = unit_mapping.get(unit)

    if not window_seconds:
        logger.warning("unsupported_rate_limit_unit", raw=rate_limit)
        return None

    if max_requests <= 0 or window_seconds <= 0:
        logger.warning("non_positive_rate_limit", raw=rate_limit)
        return None

    return max_requests, window_seconds


def _enforce_competitor_scrape_rate_limit(user_id: UUID) -> None:
    """Garante que requisições de scraping respeitam limites configurados por usuário."""

    parsed_limit = _parse_rate_limit_config(settings.COMPETITOR_RATE_LIMIT)
    if not parsed_limit:
        return

    max_requests, window_seconds = parsed_limit
    leak_rate = max_requests / window_seconds
    bucket_key = f"rate:competitor:{user_id}"

    allowed, _ = consume_leaky_bucket(
        bucket_key,
        capacity=max_requests,
        leak_rate_per_second=leak_rate,
    )

    if not allowed:
        logger.warning(
            "competitor_rate_limit_exceeded",
            user_id=str(user_id),
            limit=max_requests,
            window=window_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de scraping de concorrentes atingido. Tente novamente em instantes.",
        )

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
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        monitored_id=str(product_data.monitored_product_id),
    )

    try:
        normalized_url, issue = normalize_and_validate_product_url(str(product_data.product_url))
    except ValueError as exc:
        logger.warning("invalid_competitor_url", url=str(product_data.product_url), error=str(exc))
        error_payload = {"detail": str(exc)}
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_payload["detail"])

    if issue:
        logger.warning("invalid_competitor_url", url=normalized_url, code=issue.code)
        error_payload = {"detail": issue.message}
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
            "competitor_exists",
            path=request.url.path,
            method=request.method,
            monitored_id=str(mp.id),
            competitor_id=str(existing.id),
        )
        conflict_payload = {"detail": "Concorrente já cadastrado para este produto monitorado."}
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=conflict_payload["detail"],
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

    try:
        _enforce_competitor_scrape_rate_limit(user.id)
    except HTTPException as exc:
        error_payload = exc.detail if isinstance(exc.detail, dict) else {"detail": str(exc.detail)}
        raise

    pending = create_pending_competitor_product(
        db=db,
        monitored_product_id=mp.id,
        product_url=normalized_url,
    )

    #Cria um produto concorrente via Celery
    collect_competitor_task.delay(
        monitored_product_id=str(product_data.monitored_product_id),
        url=normalized_url,
    )

    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="scheduled",
        competitor_id=str(pending.id),
    )
    response_payload = CompetitorScrapeCreationResponse(
        id=pending.id,
        url=pending.product_url,
        created_at=pending.created_at,
        message="Scraping de concorrente agendado com sucesso.",
    )

    return response_payload

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
    visible_total = len(items)
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

    #Mantemos o total real retornado pela consulta paginada para consistência da API
    return PaginatedCompetitorResponse(
        items=items,
        meta=PaginationMeta(total=total, page=page, per_page=per_page)
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
