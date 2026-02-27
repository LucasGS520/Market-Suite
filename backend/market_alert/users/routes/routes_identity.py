""" Rotas de verificação de identidade vinculadas ao contexto de usuário """

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from shared.infra.db import get_db

from market_alert.infraestructure.security.auth_context import get_current_user
from market_alert.models.models_users import User
from market_alert.schemas.schemas_users import VerificationResendRequest
from market_alert.users.services import resend_verification


router = APIRouter(prefix="/users", tags=["Usuários"])
logger = structlog.get_logger("users.routes.identity")

@router.post("/resend-verification")
def resend_verification_tokens(
    request: Request,
    payload: VerificationResendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ Endpoint para reenviar tokens de verificação """
    logger.info("route_called", path=request.url.path, method=request.method, user_id=str(current_user.id))
    resend_verification(db, current_user, payload, request)
    logger.info("route_completed", path=request.url.path, method=request.method, status="success", user_id=str(current_user.id))
    return {"msg": "Verificação reenviada com sucesso."}
