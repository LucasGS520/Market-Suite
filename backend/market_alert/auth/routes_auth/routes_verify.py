""" Rotas para verificação de email e telefone """

import structlog
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from shared.infra.db import get_db
from market_alert.schemas.schemas_auth import PhoneOtpRequest
from market_alert.services.services_users import verify_email, verify_phone_otp


logger = structlog.get_logger("route.auth.verify")
router = APIRouter(prefix="/auth", tags=["Verificação"])

@router.post("/verify-email")
def confirm_email(token: str = Query(...), db: Session = Depends(get_db)):
    """ Confirma o token de verificação de email """
    logger.info("verify_email_called", current_token=bool(token))
    verify_email(db, token)
    return {"msg": "E-mail verificado com sucesso."}

@router.post("/verify-phone")
def confirm_phone(payload: PhoneOtpRequest, db: Session = Depends(get_db)):
    """ Confirma o OTP de telefone """
    logger.info("verify_phone_called", user_id=payload.user_id)
    verify_phone_otp(db, UUID(payload.user_id), payload.otp)
    return {"msg": "Telefone verificado com sucesso."}
