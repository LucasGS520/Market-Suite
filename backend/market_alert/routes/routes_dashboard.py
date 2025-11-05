""" Rotas responsáveis por consolidar estátisticas rápidas do dashboard """

import structlog
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from shared.infra.db import get_db
from market_alert.core.security import get_current_user
from market_alert.models import User
from market_alert.models.models_products import MonitoredProduct
from market_alert.models.models_alerts import AlertRule
from market_alert.enums.enums_products import MonitoredStatus


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
logger = structlog.get_logger("dashboard_routes")

def _convert_decimal(value: Decimal | float | int | None) -> float:
    """ Converte valores decimais para float para facilitar serialização JSON """
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)

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
        db.query(func.count(MonitoredProduct.id))
        .filter(
            MonitoredProduct.user_id == user.id,
            MonitoredProduct.status == MonitoredStatus.active,
            MonitoredProduct.target_price.isnot(None),
            MonitoredProduct.current_price.isnot(None),
            MonitoredProduct.current_price <= MonitoredProduct.target_price,
        )
        .scalar()
        or 0
    )

    #Calcula somente a diferença de preço para itens cujo valor atual excede a meta definida
    savings_case = case(
        (
            MonitoredProduct.target_price.isnot(None)
            & MonitoredProduct.current_price.isnot(None)
            & (MonitoredProduct.current_price > MonitoredProduct.target_price),
            MonitoredProduct.current_price - MonitoredProduct.target_price,
        ),
        else_=0,
    )

    potential_savings_raw = (
        db.query(func.coalesce(func.sum(savings_case), 0))
        .filter(
            MonitoredProduct.user_id == user.id,
            MonitoredProduct.status == MonitoredStatus.active,
        )
        .scalar()
    )

    stats = {
        "total_monitored": int(total_monitored),
        "active_alerts": int(active_alerts),
        "ok_prices": int(ok_prices),
        "potential_savings": _convert_decimal(potential_savings_raw),
    }

    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        **stats,
    )
    return stats
