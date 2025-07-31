""" Rotas para recuperação e redefinição de senha """

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from infra.db import get_db
from app.schemas.schemas_auth import ResetPasswordRequest, ResetPasswordConfirmRequest
from app.services.services_auth import request_password_reset_service, confirm_password_service


logger = structlog.get_logger("route.auth.reset")
router = APIRouter(prefix="/auth/reset_password", tags=["Reset da Senha"])

@router.post("/request")
def request_reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """ Solicita token para reset de senha. """
    logger.info("reset_request_called", email=payload.email)
    request_password_reset_service(db, payload)
    return {"msg": "Instruções de reset enviadas por e-mail."}

@router.post("/confirm")
def confirm_reset_password(payload: ResetPasswordConfirmRequest, db: Session = Depends(get_db)):
    """ Confirma token e atualiza a senha """
    logger.info("reset_confirm_called", token=payload.token)
    confirm_password_service(db, payload)
    return {"msg": "Senha atualizada com sucesso."}
