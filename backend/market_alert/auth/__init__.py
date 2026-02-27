"""Facade pública da feature de autenticação.

Centraliza exports de rotas e serviços usados externamente.
"""

from market_alert.auth.routes_auth import (
    login_router,
    logout_router,
    profile_router,
    refresh_router,
    reset_password_router,
    verify_router,
)
from market_alert.auth.services import (
    change_email_service,
    change_password_service,
    confirm_email_verification_service,
    confirm_password_service,
    login_user,
    refresh_token_service,
    request_password_reset_service,
)

__all__ = [
    "login_router",
    "logout_router",
    "profile_router",
    "refresh_router",
    "reset_password_router",
    "verify_router",
    "login_user",
    "refresh_token_service",
    "confirm_email_verification_service",
    "request_password_reset_service",
    "confirm_password_service",
    "change_password_service",
    "change_email_service",
]
