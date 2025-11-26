""" Rotas responsáveis por consolidar estátisticas rápidas do dashboard """

import structlog

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from shared.infra.db import get_db
from market_alert.core.security import get_current_user
from market_alert.models import User
from market_alert.services.services_dashboard import gather_dashboard_totals


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
logger = structlog.get_logger("dashboard_routes")

@router.get("/stats")
def get_dashboard_stats(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
) -> dict[str, int]:
    """ Retorna os totais principais exibidos no dashboard """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id))
   
    stats = gather_dashboard_totals(db=db, user=user)
    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        **stats,
    )
    return stats
