""" Rotas de autenticação de usuários """

import structlog
from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from shared.infra.db import get_db

from market_alert.schemas.schemas_auth import TokenPairResponse
from market_alert.auth.services.services_auth import login_user
from market_alert.auth.utils.cookies_auth import set_refresh_cookie


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
    token_pair = login_user(request, db, form_data.username, form_data.password)
    set_refresh_cookie(response, token_pair.refresh_token, request)
    return token_pair
