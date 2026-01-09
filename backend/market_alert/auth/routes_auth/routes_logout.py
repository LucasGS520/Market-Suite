""" Rotas de logout de usuários """

import structlog
from fastapi import APIRouter, Depends, status, Request, Response
from sqlalchemy.orm import Session

from shared.infra.db import get_db
from market_alert.schemas.schemas_auth import RefreshRequest
from market_alert.auth.services_auth import logout_service
from market_alert.auth.cookies_auth import clear_refresh_cookie


logger = structlog.get_logger("route.auth.logout")
router = APIRouter(prefix="/auth", tags=["Autenticação"])

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, payload: RefreshRequest | None = None, db: Session = Depends(get_db)):
    """ Revoga o Refresh Token enviado, encerrando a sessão """
    #Não registramos tokens crus para prevenir vazamento de credenciais nos logs.
    logger.info(
        "logout_route_called",
        ip=request.client.host,
        token_presente=bool(payload and payload.refresh_token),
    )
    logout_service(db, payload, request)
    clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
