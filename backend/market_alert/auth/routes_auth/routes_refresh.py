""" Rotas para renovação de tokens de autenticação """

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from shared.infra.db import get_db
from market_alert.schemas.schemas_auth import RefreshRequest, TokenPairResponse
from market_alert.auth.services_auth import refresh_token_service


logger = structlog.get_logger("route.auth.refresh")
router = APIRouter(prefix="/auth", tags=["Autenticação"])

@router.post("/refresh", response_model=TokenPairResponse)
def refresh_tokens(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    """ Troca um Refresh Token válido por um novo par de tokens (access + refresh) """
    #Evitamos registrar o valor do refresh token para não expor segredos em logs.
    logger.info(
        "refresh_route_called",
        ip=request.client.host,
        token_presente=bool(payload.refresh_token),
    )
    return refresh_token_service(db, payload, request)
