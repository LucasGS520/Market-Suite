""" Rotas para recuperação e redefinição de senha """

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from shared.infra.db import get_db

from market_alert.schemas.schemas_auth import ResetPasswordRequest, ResetPasswordConfirmRequest
from market_alert.auth.services.services_auth import request_password_reset_service, confirm_password_service
from market_alert.infrastructure.security.client_identity import resolve_client_ip


logger = structlog.get_logger("route.auth.reset")
router = APIRouter(prefix="/auth/reset_password", tags=["Reset da Senha"])

@router.post("/request")
def request_reset_password(request: Request, payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """ Solicita token para reset de senha. """
    logger.info("reset_request_called", ip=resolve_client_ip(request), email=payload.email)
    request_password_reset_service(db, payload, request)
    return {"msg": "Instruções de reset enviadas por e-mail."}

@router.post("/confirm")
def confirm_reset_password(request: Request, payload: ResetPasswordConfirmRequest, db: Session = Depends(get_db)):
    """ Confirma token e atualiza a senha """
    logger.info("reset_confirm_called", ip=resolve_client_ip(request))
    confirm_password_service(db, payload, request)
    return {"msg": "Senha atualizada com sucesso."}
