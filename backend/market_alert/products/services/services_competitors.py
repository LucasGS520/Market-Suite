""" Consultas de leitura para produtos concorrentes.

Responsabilidade única: listar concorrentes com paginação e enriquecimento.

Este arquivo é read-only — não altera estado, não enfileira, não remove.
Para operações de ciclo de vida (criar, deletar), use:
    market_alert.services.services_competitor_lifecycle
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import HTTPException
from sqlalchemy.orm import Session

from market_alert.models import User
from market_alert.schemas.schemas_products import CompetitorsListResponse
from market_alert.products.crud.crud_competitor import paginate_competitors
from market_alert.products.services.services_products import build_competitor_response
from market_alert.products.services.services_access_control import ensure_user_can_access_monitored


logger = structlog.get_logger(__name__)

def list_competitors_with_pagination(
    *,
    db: Session,
    user: User,
    monitored_product_id: UUID,
    page: int,
    per_page: int,
    include_inactive: bool,
    include_paused: bool,
    context: dict[str, str] | None = None,
) -> CompetitorsListResponse:
    """ Coordena validação de acesso, filtros e paginação de concorrentes """
    ensure_user_can_access_monitored(
        db=db,
        product_id=monitored_product_id,
        user=user,
        context=context,
        hide_forbidden=False,
    )

    total, with_price_count, excluded_count, competitors = paginate_competitors(
        db,
        monitored_product_id,
        page=page,
        per_page=per_page,
        include_inactive=include_inactive,
        include_paused=include_paused,
    )

    items: list = []
    for competitor in competitors:
        try:
            items.append(build_competitor_response(competitor, allow_missing_price=True))
        except HTTPException as exc:
            #Ignora concorrentes incompletos preservando previsibilidade da listagem
            logger.warning(
                "competitor_without_price",
                competitor_id=str(competitor.id),
                monitored_id=str(monitored_product_id),
                status=competitor.status.value,
                detail=str(exc.detail),
                **(context or {}),
            )
            continue

    return CompetitorsListResponse(
        items=items,
        competitors_total=total,
        competitors_with_price_count=with_price_count,
        excluded_due_to_inactive_count=excluded_count,
        page=page,
        per_page=per_page,
    )
