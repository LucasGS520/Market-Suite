""" Rotas de autenticação de usuários """

import structlog
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import app.metrics as metrics
from infra.db import get_db
from app.schemas.schemas_auth import TokenResponse
from app.services.services_auth import login_user


logger = structlog.get_logger("route.auth.login")
router = APIRouter(prefix="/auth", tags=["Autenticação"])

@router.post("/", response_model=TokenResponse)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """ Autentica o usuário e retorna um JWT. Aplica bloqueio de IP e registro de tentativas """
    logger.info("login_route_called", ip=request.client.host, email=form_data.username)
    try:
        return login_user(request, db, form_data.username, form_data.password)
    except HTTPException as exc:
        #Conta apenas falhas de credenciais inválidas
        if exc.status_code == 401:
            metrics.LOGIN_ERRORS_TOTAL.labels(reason="invalid_credentials").inc()
        raise
