""" Serviços de controle de acesso para recursos monitorados """

from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from market_alert.crud.crud_monitored import get_monitored_product_by_id
from market_alert.models import User
from market_alert.models.models_products import MonitoredProduct


logger = structlog.get_logger(__name__)

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
