""" Rotas de gestão de conta de usuários """

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from shared.infra.db import get_db

from market_alert.infraestructure.security.auth_context import get_current_user
from market_alert.models.models_users import User
from market_alert.schemas.schemas_users import UserCreate, UserResponse, UserUpdate
from market_alert.users.services import (
    change_user_status,
    read_my_profile,
    register_user,
    update_user as service_update_user,
    validate_phone_number,
)


logger = structlog.get_logger("users.routes.account")
router = APIRouter(prefix="/users", tags=["Usuários"])

def _validate_admin_permission(current_user: User) -> None:
    """ Restringe endpoints administrativos a contas com papel admin """
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permissão negada: apenas administradores")

@router.post("/", response_model=UserResponse)
def add_user(
    request: Request,
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """ Cadastra novo usuário e inicia verificações iniciais """
    validate_phone_number(user_data.phone_number)
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        email=user_data.email,
    )
    user = register_user(db, user_data, request)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", user_id=str(user.id))
    return user

@router.put("/{user_id}/status", response_model=UserResponse)
def change_status(
    request: Request,
    user_id: UUID,
    active: bool,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ Ativa ou suspende conta alvo """
    _validate_admin_permission(current_user)
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        target_user=str(user_id),

    )
    user = change_user_status(db, user_id, active)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", user_id=str(user.id))
    return user

@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    request: Request,
    user_id: UUID,
    updates: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ Atualiza dados administrativos do usuário """
    _validate_admin_permission(current_user)
    validate_phone_number(updates.phone_number)
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        target_user=str(user_id),
        actor_id=str(current_user.id),
    )
    user = service_update_user(db, user_id, updates)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", user_id=str(user.id))
    return user

@router.get("/me", response_model=UserResponse)
def read_my_profile(request: Request, current_user: User = Depends(get_current_user)):
    """ Endpoint para vizualizar dados do usuário autenticado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(current_user.id))
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", user_id=str(current_user.id))
    return current_user
