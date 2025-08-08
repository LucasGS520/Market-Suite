""" Rotas de gerenciamento de perfil do usuário """

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from infra.db import get_db
from alert_app.schemas.schemas_auth import ChangePasswordRequest, ChangeEmailRequest
from alert_app.services.services_auth import change_password_service, change_email_service
from alert_app.core.security import get_current_user
from alert_app.models.models_users import User


logger = structlog.get_logger("route.auth.profile")
router = APIRouter(prefix="/auth", tags=["Perfil de Usuário"])

@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """ Permite ao usuário autenticado alterar a sua senha """
    logger.info("change_password_route_called", user_id=str(current_user.id))
    change_password_service(db, current_user, payload)
    return {"msg": "Senha alterada com sucesso."}

@router.post("/change-email")
def change_email(payload: ChangeEmailRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """ Permite ao usuário autenticado alterar seu email """
    logger.info("change_email_route_called", user_id=str(current_user.id), new_email=payload.new_email)
    change_email_service(db, current_user, payload)
    return {"msg": "E-mail alterado. Verifique novamente seu e-mail."}
