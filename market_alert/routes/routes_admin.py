""" Rotas exclusivas para administração e gerenciamento de usuários """

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from uuid import UUID

from infra.db import get_db
from alert_app.core.security import get_current_admin_user
from alert_app.models.models_users import User


logger = structlog.get_logger("http_route")
router = APIRouter(prefix="/admin", tags=["Administradores"])

@router.get("/dashboard")
def admin_dashboard(request: Request, current_user: User = Depends(get_current_admin_user)):
    """ Retorna mensagem de boas-vindas para o administrador autenticado """
    logger.info("route_called", path=request.url.path, method=request.method, user_email=current_user.email)
    msg = {"msg": f"Bem-vindo, administrador {current_user.email}"}
    logger.info("route_completed", path=request.url.path, method=request.method, status="success")
    return msg

@router.get("/users")
def list_users(request: Request, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    """ Lista usuários cadastrados """
    logger.info("route_called", path=request.url.path, method=request.method, user_email=admin.email)
    users = db.query(User).all()
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", count=len(users))
    return users

@router.patch("/activate/{user_id}")
def activate_user(request: Request, user_id: UUID, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    """ Ativar usuários """
    logger.info("route_called", path=request.url.path, method=request.method, user_email=admin.email, target_user=str(user_id))
    #Busca usuário no banco
    user = db.query(User).filter(User.id == user_id).first()
    #Confirma se o usuário existe
    if not user:
        logger.warning("route_error", reason="not_found", target_user=str(user_id))
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.is_active = True
    db.commit()
    logger.info("route_completed", path=request.url.path, method=request.method, status="success")
    return {"msg": "Usuário ativado com sucesso."}

@router.patch("/deactivate/{user_id}")
def deactivate_user(request: Request, user_id: UUID, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    """ Desativar usuários"""
    logger.info("route_called", path=request.url.path, method=request.method, user_email=admin.email, target_user=str(user_id))
    #Busca usuário no banco
    user = db.query(User).filter(User.id == user_id).first()
    #Confirma se o usuário existe
    if not user:
        logger.warning("route_error", reason="not_found", target_user=str(user_id))
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.is_active = False
    db.commit()
    logger.info("route_completed", path=request.url.path, method=request.method, status="success")
    return {"msg": "Usuário desativado com sucesso."}

@router.delete("/delete/{user_id}")
def delete_user(request: Request, user_id: UUID, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    """ Deletar usuários (Atenção e cuidado) """
    logger.info("route_called", path=request.url.path, method=request.method, user_email=admin.email, target_user=str(user_id))
    #Busca usuário no banco
    user = db.query(User).filter(User.id == user_id).first()
    #Confirma se o usuário existe
    if not user:
        logger.warning("route_error", reason="not_found", target_user=str(user_id))
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    db.delete(user)
    db.commit()
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", target_user=str(user_id))
    return {"msg": "Usuário deletado com sucesso."}

@router.put("/promote/{user_id}")
def promote_user_to_admin(request: Request, user_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    """ Eleva o usuário indicado ao papel de administrador """
    logger.info("route_called", path=request.url.path, method=request.method, user_email=current_user.email, target_user=str(user_id))
    #Busca usuário no banco
    user = db.query(User).filter(User.id == user_id).first()
    #Confirma se usuário existe
    if not user:
        logger.warning("route_error", reason="not_found", target_user=str(user_id))
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.role = "admin"
    db.commit()
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", target_user=str(user_id))
    return {"msg": f"Usuário {user.email} promovido a administrador"}
