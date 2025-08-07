""" Rotas para verificação de email """

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from infra.db import get_db
from alert_app.schemas.schemas_auth import EmailTokenRequest
from alert_app.services.services_auth import send_verification_email_service, confirm_email_verification_service
from alert_app.core.security import get_current_user
from alert_app.models.models_users import User


logger = structlog.get_logger("route.auth.verify")
router = APIRouter(prefix="/auth/verify", tags=["Verificação de E-mail"])

@router.post("/request")
def request_verification(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """ Gera um token de verificação e envia por email """
    logger.info("verify_request_called", user_id=str(current_user.id))
    send_verification_email_service(db, current_user)
    return {"msg": "Token de verificação enviado por e-mail."}

@router.post("/confirm")
def confirm_verification(payload: EmailTokenRequest, db: Session = Depends(get_db)):
    """ Confirma o token de verificação de email """
    logger.info("verify_confirm_called", token=payload.token)
    confirm_email_verification_service(db, payload)
    return {"msg": "E-mail verificado com sucesso."}
