""" Utilitários para manipular cookies de autenticação de forma segura """

import os

from fastapi import Request, Response

from market_alert.core.config_alert import settings


def _resolve_refresh_cookie_settings(request: Request | None = None) -> tuple[bool, str]:
    """ Normaliza os parâmetros do cookie de refresh conforme o ambiente """
    secure = settings.REFRESH_TOKEN_COOKIE_SECURE
    samesite = (settings.REFRESH_TOKEN_COOKIE_SAMESITE or "lax").strip().lower()
    env_secure = os.getenv("REFRESH_TOKEN_COOKIE_SECURE")
    env_samesite = os.getenv("REFRESH_TOKEN_COOKIE_SAMESITE")
    if request and request.url.scheme == "http" and env_secure is None:
        #Fallback defensivo para ambiente local sem HTTPS quando a flag não foi configurada
        secure = False
    if request and request.url.scheme == "http" and env_samesite is None and samesite in {"lax", "strict"}:
        #Alinha SameSite para permitir envio cross-site no dev sem exigir configuração manual
        samesite = "none"
    allowed = {"lax", "strict", "none"}
    if samesite not in allowed:
        #Fallback defensivo evita valores inválidos vindos do .env
        samesite = "lax"
    if samesite == "none" and not secure:
        #Permite SameSite=None em HTTP local quando frontend está em outro host/porta
        return secure, samesite
    return secure, samesite

def set_refresh_cookie(response: Response, refresh_token: str, request: Request | None = None) -> None:
    """ Define o cookie HttpOnly de refresh token na resposta """
    max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    secure, samesite = _resolve_refresh_cookie_settings(request)
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path=settings.REFRESH_TOKEN_COOKIE_PATH,
        max_age=max_age,
    )

def clear_refresh_cookie(response: Response) -> None:
    """ Remove o cookie HttpOnly de refresh token da resposta """
    response.delete_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        path=settings.REFRESH_TOKEN_COOKIE_PATH,
    )
    