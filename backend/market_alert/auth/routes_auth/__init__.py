"""Facade de roteadores HTTP da feature de autenticação."""

from market_alert.auth.routes_auth.routes_login import router as login_router
from market_alert.auth.routes_auth.routes_logout import router as logout_router
from market_alert.auth.routes_auth.routes_profile import router as profile_router
from market_alert.auth.routes_auth.routes_refresh import router as refresh_router
from market_alert.auth.routes_auth.routes_reset_password import (
    router as reset_password_router,
)
from market_alert.auth.routes_auth.routes_verify import router as verify_router

__all__ = [
    "login_router",
    "logout_router",
    "profile_router",
    "refresh_router",
    "reset_password_router",
    "verify_router",
]
