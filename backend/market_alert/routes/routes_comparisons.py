""" Rotas para consulta de comparações de preços """

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from uuid import UUID

from shared.infra.db import get_db
from market_alert.models import User
from market_alert.schemas.schemas_comparisons import (
    PaginatedPriceComparisonResponse,
    PriceComparisonResponse,
    PriceComparisonSummaryResponse,
)
from market_alert.core.security import get_current_user
from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.crud.crud_comparison import (
    get_comparison_by_id,
    get_latest_comparisons_for_products,
    get_latest_summary,
    paginate_comparisons,
)
from market_alert.services.services_comparison import build_comparison_summary


router = APIRouter(prefix="/comparisons", tags=["Comparações"])
logger = structlog.get_logger("http_route")

@router.get("/{monitored_id}", response_model=PaginatedPriceComparisonResponse)
def list_comparisons(
    request: Request,
    monitored_id: UUID,
    page: int = Query(
        1,
        ge=1,
        description="Página atual do histórico de comparações (base 1)",
    ),
    per_page: int = Query(
        20,
        ge=1,
        le=100,
        description="Quantidade de registros retornados por página",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ Lista histórico de comparações aplicando envelope de paginação estável """
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        monitored_id=str(monitored_id),
        page=page,
        per_page=per_page,
    )

    mp = get_monitored_product_by_id(db, monitored_id)
    if not mp or mp.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", monitored_id=str(monitored_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto monitorado não encontrado.")

    total, comparisons = paginate_comparisons(
        db,
        monitored_product_id=monitored_id,
        page=page,
        per_page=per_page,
    )
    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        count=len(comparisons),
        total=total,
    )
    return PaginatedPriceComparisonResponse(
        items=comparisons,
        meta={"total": total, "page": page, "per_page": per_page},
    )

@router.get("/{monitored_id}/summary", response_model=PriceComparisonSummaryResponse)
def get_comparison_summary(request: Request, monitored_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Retorna o resumo agregado da última comparação executada para o produto monitorado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), monitored_id=str(monitored_id))

    mp = get_monitored_product_by_id(db, monitored_id)
    if not mp or mp.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", monitored_id=str(monitored_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto monitorado não encontrado.")
    
    latest_comparison = get_latest_comparisons_for_products(db, [monitored_id]).get(monitored_id)
    stored_summary = get_latest_summary(db, monitored_id)
    competitors_count = len(getattr(mp, "competitors", []) or [])
    summary = build_comparison_summary(
        latest_comparison,
        competitors_count=competitors_count,
        stored_summary=stored_summary,
    )

    logger.info("route_completed", path=request.url.path, method=request.method, status="success", monitored_id=str(monitored_id))
    return PriceComparisonSummaryResponse(
        monitored_product_id=monitored_id,
        **summary,
    )

@router.get("/detail/{comparison_id}", response_model=PriceComparisonResponse)
def get_comparison(request: Request, comparison_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Obtém os detalhes de uma comparação específica """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), comparison_id=str(comparison_id))

    comparison = get_comparison_by_id(db, comparison_id)
    if not comparison:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", comparison_id=str(comparison_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparação não encontrada.")

    mp = get_monitored_product_by_id(db, comparison.monitored_product_id)
    if not mp or mp.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", monitored_id=str(comparison.monitored_product_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto monitorado não encontrado.")

    logger.info("route_completed", path=request.url.path, method=request.method, reason="success", comparison_id=str(comparison_id))
    return comparison
