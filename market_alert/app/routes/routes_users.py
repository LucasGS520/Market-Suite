""" Rotas HTTP para gerenciamento de usuários """

import structlog
from uuid import UUID
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from infra.db import get_db
from app.schemas.schemas_users import UserCreate, UserResponse, UserUpdate
from app.crud import crud_user as crud
from app.models.models_users import User
from app.core.security import get_current_user


router = APIRouter(prefix="/users", tags=["Usuários"]) #Cria um agrupador/organizador de rotas
logger = structlog.get_logger("http_route")

#Valida se o email já existe, cria o usuário e retorna os dados
@router.post("/", response_model=UserResponse)
def add_user(request: Request, user_data: UserCreate, db: Session = Depends(get_db)):
    """ Endpoint para criar um usuário"""
    logger.info("route_called", path=request.url.path, method=request.method, email=user_data.email)
    user = crud.create_user(db, user_data)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", user_id=str(user.id))
    return user

@router.put("/{user_id}/status", response_model=UserResponse)
def change_status(request: Request, user_id: UUID, active: bool, db: Session = Depends(get_db)):
    """ Endpoint para ativar e desativar um usuário """
    logger.info("route_called", path=request.url.path, method=request.method, target_user=str(user_id), active=active)
    user = crud.toggle_user_active(db, user_id, active)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", user_id=str(user.id))
    return user

@router.put("/{user_id}", response_model=UserResponse)
def update_user(request: Request, user_id: UUID, updates: UserUpdate, db: Session = Depends(get_db)):
    """ Endpoint para atualizar usuário """
    logger.info("route_called", path=request.url.path, method=request.method, target_user=str(user_id))
    user = crud.update_user(db, user_id, updates)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", user_id=str(user.id))
    return user

@router.get("/me", response_model=UserResponse)
def read_my_profile(request: Request, current_user: User = Depends(get_current_user)):
    """ Endpoint para vizualizar dados do usuário autenticado """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(current_user.id))
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", user_id=str(current_user.id))
    return current_user
