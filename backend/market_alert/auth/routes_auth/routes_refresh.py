""" Rotas para renovação de tokens de autenticação """

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from shared.infra.db import get_db

from market_alert.core.config_alert import settings
from market_alert.schemas.schemas_auth import RefreshRequest, TokenPairResponse
from market_alert.auth.services.services_auth import refresh_token_service
from market_alert.auth.utils.cookies_auth import set_refresh_cookie
from market_alert.infrastructure.security.client_identity import resolve_client_ip


logger = structlog.get_logger("route.auth.refresh")
router = APIRouter(prefix="/auth", tags=["Autenticação"])

@router.post("/refresh", response_model=TokenPairResponse)
def refresh_tokens(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = None,
    db: Session = Depends(get_db),
):
    """ Troca um Refresh Token válido por um novo par de tokens (access + refresh) """
    #Evitamos registrar o valor do refresh token para não expor segredos em logs.
    request_id = request.headers.get("x-request-id") or request.headers.get("x-requestid")
    cookie_token = request.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    logger.info(
        "refresh_route_called",
        ip=resolve_client_ip(request),
        request_id=request_id,
        cookie_current=bool(cookie_token),
        payload_current=bool(payload and payload.refresh_token),
    )
    token_pair = refresh_token_service(db, payload, request)
    set_refresh_cookie(response, token_pair.refresh_token, request)
    return token_pair
