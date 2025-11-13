""" Serviços de apoio para rotinas de concorrentes monitorados """

from __future__ import annotations

from typing import Iterable
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from market_alert.models import User
from market_alert.models.models_products import CompetitorProduct, MonitoredProduct
from market_alert.schemas.schemas_products import CompetitorListItemResponse
from market_alert.crud.crud_monitored import get_monitored_product_by_id


logger = structlog.get_logger(__name__)


def format_decimal_field(value) -> str | None:
    """ Formata valores decimais para string preservando `None` """
    if value is None:
        return None
    return str(value)


def calculate_price_change(competitor: CompetitorProduct) -> tuple[str | None, str | None]:
    """ Calcula variação absoluta e percentual entre preços atual e anterior """
    current = competitor.current_price
    previous = competitor.old_price

    if current is None or previous is None:
        return None, None

    absolute_change = current - previous
    try:
        percentage_change = (absolute_change / previous) * 100 if previous else None
    except ZeroDivisionError:
        #Evita quebra quando o preço anterior está zerado
        percentage_change = None

    absolute_str = format_decimal_field(absolute_change)
    percentage_str = None

    if percentage_change is not None:
        percentage_str = f"{percentage_change:.4f}"

    return absolute_str, percentage_str


def map_competitor_to_response(competitor: CompetitorProduct) -> CompetitorListItemResponse:
    """ Normaliza modelo ORM para o contrato de listagem de concorrentes """
    absolute_change, percentage_change = calculate_price_change(competitor)

    return CompetitorListItemResponse(
        id=competitor.id,
        monitored_product_id=competitor.monitored_product_id,
        name=competitor.name_competitor,
        product_url=competitor.product_url,
        current_price=format_decimal_field(competitor.current_price),
        previous_price=format_decimal_field(competitor.old_price),
        price_change=absolute_change,
        price_change_percentage=percentage_change,
        status=competitor.status,
        last_checked=competitor.last_checked,
        is_paused=competitor.is_paused,
    )


def ensure_user_can_access_monitored(
    *,
    db: Session,
    product_id: UUID,
    user: User,
    context: dict[str, str] | None = None,
    hide_forbidden: bool = True,
) -> MonitoredProduct:
    """ Valida vínculo do monitorado com o usuário autenticado """
    log_context: dict[str, str] = {"monitored_id": str(product_id)}
    if context:
        log_context.update(context)

    monitored = get_monitored_product_by_id(db, product_id)

    if monitored is None:
        logger.warning("monitored_not_found", **log_context)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto monitorado não encontrado.",
        )

    if monitored.user_id != user.id:
        log_context["owner_id"] = str(monitored.user_id)

        if hide_forbidden:
            #Oculta detalhes para evitar exposição de dados sensíveis
            logger.warning("monitored_forbidden_hidden", **log_context)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Produto monitorado não encontrado.",
            )

        logger.warning("monitored_forbidden", **log_context)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário não possui permissão para acessar este produto monitorado.",
        )

    return monitored


def load_competitors_for_action(
    *,
    db: Session,
    monitored_product_id: UUID,
    competitor_ids: Iterable[UUID],
) -> list[CompetitorProduct]:
    """ Carrega concorrentes garantindo vínculo com o monitorado informado """
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


def validate_competitor_limit(
    *,
    db: Session,
    monitored_product_id: UUID,
    limit: int,
    count_competitors_callback,
    context: dict[str, str] | None = None,
) -> None:
    """ Garante que o monitorado respeita o limite máximo de concorrentes """
    log_context = {"monitored_id": str(monitored_product_id), "limit": limit}
    if context:
        log_context.update(context)

    competitors_total = count_competitors_callback(db, monitored_product_id, include_paused=True)

    if competitors_total >= limit:
        logger.warning("competitor_limit_reached", **log_context)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Limite de concorrentes atingido para este produto monitorado.",
        )
    