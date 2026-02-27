"""Facade de roteadores HTTP da feature de usuários.

Esta composição reduz acoplamento da aplicação com nomes de arquivos internos.
"""

from market_alert.users.routes.routes_account import router as account_router
from market_alert.users.routes.routes_identity import router as identity_router
from market_alert.users.routes.routes_settings import router as settings_router

__all__ = ["account_router", "identity_router", "settings_router"]
