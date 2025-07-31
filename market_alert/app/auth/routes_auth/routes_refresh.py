""" Rotas para renovação de tokens de autenticação """

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from infra.db import get_db
from app.schemas.schemas_auth import RefreshRequest, TokenPairResponse
from app.services.services_auth import refresh_token_service


logger = structlog.get_logger("route.auth.refresh")
router = APIRouter(prefix="/auth", tags=["Autenticação"])

@router.post("/refresh", response_model=TokenPairResponse)
def refresh_tokens(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    """ Troca um Refresh Token válido por um novo par de tokens (access + refresh) """
    logger.info("refresh_route_called", token=payload.refresh_token, ip=request.client.host)
    return refresh_token_service(db, payload, request)
