""" Rotas HTTP para gerenciamento de usuários com autenticação e autorização """

import re
import structlog
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from shared.infra.db import get_db
from market_alert.schemas.schemas_users import UserCreate, UserResponse, UserUpdate
from market_alert.models.models_users import User
from market_alert.core.security import get_current_user
from market_alert.services.services_users import (
    change_user_status,
    create_user,
    update_user as service_update_user,
)


router = APIRouter(prefix="/users", tags=["Usuários"]) #Cria um agrupador/organizador de rotas
logger = structlog.get_logger("http_route")

def _validate_admin_permission(current_user: User) -> None:
    """ Garante que apenas administradores executem operações de gestão de contas """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissão negada: apenas administradores"
        )
    
def _validate_phone_number(phone_number: str | None) -> None:
    """ Confirma se o telefone foi informado no padrão E.164 """
    if phone_number and not re.fullmatch(r"\+\d{10,15}", phone_number):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Número de telefone inválido, use o padrão E.164 (ex: +5511999999999)"
        )

#Valida se o email já existe, cria o usuário e retorna os dados
@router.post("/", response_model=UserResponse)
def add_user(
    request: Request,
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """ Endpoint público para criar um usuário """
    # Esta rota permanece aberta para permitir o cadastro inicial de usuários antes de qualquer autenticação
    _validate_phone_number(user_data.phone_number)
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        email=user_data.email,
    )
    user = create_user(db, user_data)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", user_id=str(user.id))
    return user

@router.put("/{user_id}/status", response_model=UserResponse)
def change_status(
    request: Request,
    user_id: UUID,
    active: bool,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """ Endpoint para ativar e desativar um usuário """
    _validate_admin_permission(current_user)
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        target_user=str(user_id),
        active=active,
        actor_id=str(current_user.id),
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
    db: Session = Depends(get_db)
):
    """ Endpoint para atualizar usuário """
    _validate_admin_permission(current_user)
    _validate_phone_number(updates.phone_number)
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
