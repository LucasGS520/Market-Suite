""" Rotas de gerenciamento de perfil do usuário """

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from shared.infra.db import get_db

from market_alert.infrastructure.security.auth_context import get_current_user
from market_alert.infrastructure.security.client_identity import resolve_client_ip
from market_alert.models.models_users import User
from market_alert.schemas.schemas_auth import ChangePasswordRequest, ChangeEmailRequest
from market_alert.auth.services.services_auth import change_password_service, change_email_service


logger = structlog.get_logger("route.auth.profile")
router = APIRouter(prefix="/auth", tags=["Perfil de Usuário"])

@router.post("/change-password")
def change_password(request: Request, payload: ChangePasswordRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """ Permite ao usuário autenticado alterar a sua senha """
    logger.info("change_password_route_called", user_id=str(current_user.id), ip=resolve_client_ip(request))
    change_password_service(db, current_user, payload)
    return {"msg": "Senha alterada com sucesso."}

@router.post("/change-email")
def change_email(request: Request, payload: ChangeEmailRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """ Permite ao usuário autenticado alterar seu email """
    logger.info("change_email_route_called", user_id=str(current_user.id), ip=resolve_client_ip(request), new_email=payload.new_email)
    change_email_service(db, current_user, payload)
    return {"msg": "E-mail alterado. Verifique novamente seu e-mail."}
