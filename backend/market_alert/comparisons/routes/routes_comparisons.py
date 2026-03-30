""" Rotas para consulta de comparações de preços """

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from uuid import UUID

from shared.infra.db import get_db

from market_alert.models import User
from market_alert.schemas.schemas_comparisons import PriceComparisonResponse, PriceComparisonSummaryResponse
from market_alert.infrastructure.security.auth_context import get_current_user
from market_alert.comparisons.services.services_comparison import get_comparison_detail_for_user, get_comparison_summary_for_user


router = APIRouter(prefix="/comparisons", tags=["Comparações"])
logger = structlog.get_logger("http_route")

@router.get("/{monitored_id}/summary", response_model=PriceComparisonSummaryResponse)
def get_comparison_summary(
    request: Request,
    monitored_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ Retorna o resumo agregado da última comparação executada para o produto monitorado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), monitored_id=str(monitored_id))

    summary = get_comparison_summary_for_user(
        db=db,
        monitored_id=monitored_id,
        user=user,
    )

    logger.info("route_completed", path=request.url.path, method=request.method, status="success", monitored_id=str(monitored_id))
    return summary

@router.get("/detail/{comparison_id}", response_model=PriceComparisonResponse)
def get_comparison(
    request: Request,
    comparison_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ Obtém os detalhes de uma comparação específica """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id), comparison_id=str(comparison_id))

    comparison = get_comparison_detail_for_user(
        db=db,
        comparison_id=comparison_id,
        user=user,
    )

    logger.info("route_completed", path=request.url.path, method=request.method, reason="success", comparison_id=str(comparison_id))
    return comparison
