""" Rotas para consulta de comparações de preços """

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from decimal import Decimal

from infra.db import get_db
from alert_app.models import User
from alert_app.schemas.schemas_comparisons import PriceComparisonResponse
from alert_app.core.security import get_current_user
from alert_app.crud.crud_monitored import get_monitored_product_by_id
from alert_app.crud.crud_comparison import get_latest_comparisons, get_comparison_by_id
from alert_app.services.services_comparison import run_price_comparison


router = APIRouter(prefix="/comparisons", tags=["Comparações"])
logger = structlog.get_logger("http_route")

@router.get("/{monitored_id}", response_model=List[PriceComparisonResponse])
def list_comparisons(request: Request, monitored_id: UUID, limit: int = 10, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Lista as comparações recentes de um produto monitorado. """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), monitored_id=str(monitored_id))

    mp = get_monitored_product_by_id(db, monitored_id)
    if not mp or mp.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", monitored_id=str(monitored_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto monitorado não encontrado.")

    comparisons = get_latest_comparisons(db, monitored_id, limit)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", count=len(comparisons))
    return comparisons

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

@router.post("/{monitored_id}/run", response_model=dict)
def run_comparison_endpoint(request: Request, monitored_id: UUID, tolerance: float | None = Query(None), price_change_threshold: float | None = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ Execute uma nova comparação de preços para o produto monitorado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), monitored_id=str(monitored_id))

    mp = get_monitored_product_by_id(db, monitored_id)
    if not mp or mp.user_id != user.id:
        logger.warning("route_error", path=request.url.path, method=request.method, reason="not_found", monitored_id=str(monitored_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto monitorado não encontrado.")

    result, alerts = run_price_comparison(
        db,
        monitored_id,
        tolerance=Decimal(str(tolerance)) if tolerance is not None else None,
        price_change_threshold=Decimal(str(price_change_threshold)) if price_change_threshold is not None else None
    )
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", alerts=len(alerts))
    return result
