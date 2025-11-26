""" Serviços de gerenciamento de usuários centralizando regras de negócio. """

from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from market_alert.crud import crud_user
from market_alert.schemas.schemas_users import UserCreate, UserResponse, UserUpdate


logger = structlog.get_logger("service.user")

def create_user(db: Session, user_data: UserCreate) -> UserResponse:
    """ Cria um usuário aplicando validações de negócio antes do acesso ao CRUD """
    logger.debug("service_create_user", email=user_data.email)
    return crud_user.create_user(db, user_data)


def update_user(db: Session, user_id: UUID, updates: UserUpdate) -> UserResponse:
    """ Atualiza campos permitidos do usuário e evita operações sem alterações """
    update_data = updates.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nenhuma alteração informada")

    logger.debug("service_update_user", user_id=str(user_id), fields=list(update_data.keys()))
    return crud_user.update_user(db, user_id, updates)


def change_user_status(db: Session, user_id: UUID, active: bool) -> UserResponse:
    """ Altera o status de atividade do usuário garantindo rastreabilidade """
    logger.debug("service_change_user_status", user_id=str(user_id), active=active)
    return crud_user.toggle_user_active(db, user_id, active)