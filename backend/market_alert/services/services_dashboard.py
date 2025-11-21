""" Serviço responsável por consolidar totais exibidos no dashboard """

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from market_alert.enums.enums_products import MonitoredStatus
from market_alert.models import User
from market_alert.models.models_alerts import AlertRule
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct


def _active_product_filters(user: User) -> list:
    """ Prepara filtros reutilizáveis para produtos ativos do usuário """
    return [
        MonitoredProduct.user_id == user.id,
        MonitoredProduct.status == MonitoredStatus.active,
    ]

def _count_active_monitored(db: Session, filters: list) -> int:
    """ Conta produtos monitorados ativos do usuário considerando filtros comuns """
    return int(
        db.query(func.count(MonitoredProduct.id))
        .filter(*filters)
        .scalar()
        or 0
    )

def _count_competitors_from_active(db: Session, filters: list) -> int:
    """ Conta concorrentes vinculados apenas a produtos ativos do usuário """
    active_products_subquery = (
        db.query(MonitoredProduct.id)
        .filter(*filters)
        .subquery()
    )

    #Join com subconsulta garante contagem apenas de vínculos pertencentes ao usuário
    return int(
        db.query(func.count(CompetitorProduct.id))
        .join(
            active_products_subquery,
            CompetitorProduct.monitored_product_id == active_products_subquery.c.id,
        )
        .scalar()
        or 0
    )

def _count_active_alerts(db: Session, user: User) -> int:
    """ Conta alertas habilitados pelo usuário """
    return int(
        db.query(func.count(AlertRule.id))
        .filter(
            AlertRule.user_id == user.id,
            AlertRule.enabled.is_(True),
        )
        .scalar()
        or 0
    )


def _count_with_prices(db: Session, filters: list) -> int:
    """ Conta produtos ativos que já possuem preço coletado """
    return int(
        db.query(func.count(MonitoredProduct.id))
        .filter(
            *filters,
            MonitoredProduct.current_price.isnot(None),
        )
        .scalar()
        or 0
    )


def gather_dashboard_totals(db: Session, user: User) -> dict[str, int]:
    """ Calcula agregados apresentados no dashboard para o usuário autenticado.

    Centraliza a montagem das consultas SQL evitando duplicação de lógica nas
    rotas HTTP, permitindo reuso futuro em jobs ou outros pontos de entrada.
    """
    active_filters = _active_product_filters(user)

    total_monitored = _count_active_monitored(db, active_filters)
    total_competitors = _count_competitors_from_active(db, active_filters)
    active_alerts = _count_active_alerts(db, user)
    ok_prices = _count_with_prices(db, active_filters)

    return {
        "total_monitored": total_monitored,
        "total_competitors": total_competitors,
        "active_alerts": active_alerts,
        "ok_prices": ok_prices,
    }
