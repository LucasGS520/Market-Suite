""" Rotas responsáveis por consolidar estátisticas rápidas do dashboard """

import structlog

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.infra.db import get_db
from market_alert.core.security import get_current_user
from market_alert.models import User
from market_alert.models.models_products import MonitoredProduct
from market_alert.models.models_alerts import AlertRule
from market_alert.enums.enums_products import MonitoredStatus


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
logger = structlog.get_logger("dashboard_routes")

@router.get("/stats")
def get_dashboard_stats(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
) -> dict[str, float | int]:
    """ Retorna os totais principais exibidos no dashboard """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(user.id))

    #Mantém apenas produtos ativos para evitar contar itens pausados ou removidos
    active_products_query = (
        db.query(MonitoredProduct)
        .filter(
            MonitoredProduct.user_id == user.id,
            MonitoredProduct.status == MonitoredStatus.active,
        )
    )

    total_monitored = active_products_query.count()

    active_alerts = (
        db.query(func.count(AlertRule.id))
        .filter(
            AlertRule.user_id == user.id,
            AlertRule.enabled.is_(True),
        )
        .scalar()
        or 0
    )

    ok_prices = (
        active_products_query.filter(MonitoredProduct.current_price.isnot(None))
        .count()
        or 0
    )

    stats = {
        "total_monitored": int(total_monitored),
        "active_alerts": int(active_alerts),
        "ok_prices": int(ok_prices),
        "potential_savings": 0.0,
    }

    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        **stats,
    )
    return stats
