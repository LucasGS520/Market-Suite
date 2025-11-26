""" Rotas de logout de usuários """

import structlog
from fastapi import APIRouter, Depends, status, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from shared.infra.db import get_db
from market_alert.schemas.schemas_auth import RefreshRequest
from market_alert.auth.services_auth import logout_service


logger = structlog.get_logger("route.auth.logout")
router = APIRouter(prefix="/auth", tags=["Autenticação"])

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    """ Revoga o Refresh Token enviado, encerrando a sessão """
    #Não registramos tokens crus para prevenir vazamento de credenciais nos logs.
    logger.info(
        "logout_route_called",
        ip=request.client.host,
        token_presente=bool(payload.refresh_token),
    )
    logout_service(db, payload, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
