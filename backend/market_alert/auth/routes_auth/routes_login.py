""" Rotas de autenticação de usuários """

import structlog
from fastapi import APIRouter, Depends, Request, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from shared.metrics.metrics_auth import LOGIN_ERRORS_TOTAL
from shared.infra.db import get_db
from market_alert.schemas.schemas_auth import TokenPairResponse
from market_alert.auth.services_auth import login_user
from market_alert.auth.cookies_auth import set_refresh_cookie


logger = structlog.get_logger("route.auth.login")
router = APIRouter(prefix="/auth", tags=["Autenticação"])

@router.post("/login", response_model=TokenPairResponse)
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """ Autentica o usuário e retorna um JWT. Aplica bloqueio de IP e registro de tentativas """
    logger.info("login_route_called", ip=request.client.host, email=form_data.username)
    try:
        token_pair = login_user(request, db, form_data.username, form_data.password)
        set_refresh_cookie(response, token_pair.refresh_token)
        return token_pair
    except HTTPException as exc:
        #Conta apenas falhas de credenciais inválidas
        if exc.status_code == 401:
            LOGIN_ERRORS_TOTAL.labels(reason="invalid_credentials").inc()
        raise
