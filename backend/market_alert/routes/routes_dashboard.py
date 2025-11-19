""" Rotas responsáveis por consolidar estátisticas rápidas do dashboard """

import structlog

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.infra.db import get_db
from market_alert.core.security import get_current_user
from market_alert.models import User
from market_alert.models.models_products import MonitoredProduct, CompetitorProduct
from market_alert.models.models_alerts import AlertRule
from market_alert.enums.enums_products import MonitoredStatus


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

    #Mantém apenas produtos ativos para evitar contar itens pausados ou removidos
    active_filters = [
        MonitoredProduct.user_id == user.id,
        MonitoredProduct.status == MonitoredStatus.active,
    ]

    total_monitored = (
        db.query(func.count(MonitoredProduct.id))
        .filter(*active_filters)
        .scalar()
        or 0
    )

    #Subquery utilizada para somar concorrentes apenas dos produtos ativos do usuário
    active_products_subquery = db.query(MonitoredProduct.id).filter(*active_filters).subquery()

    total_competitors = (
        db.query(func.count(CompetitorProduct.id))
        .join(
            active_products_subquery,
            CompetitorProduct.monitored_product_id == active_products_subquery.c.id,
        )
        .scalar()
        or 0
    )

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
        db.query(func.count(MonitoredProduct.id))
        .filter(
            *active_filters,
            MonitoredProduct.current_price.isnot(None),
        )
        .scalar()
        or 0
    )

    stats = {
        "total_monitored": int(total_monitored),
        "total_competitors": int(total_competitors),
        "active_alerts": int(active_alerts),
        "ok_prices": int(ok_prices),
    }

    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        **stats,
    )
    return stats
