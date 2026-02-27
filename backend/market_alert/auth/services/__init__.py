"""Facade de serviços da feature de autenticação.

Importações externas devem partir daqui para evitar acoplamento em arquivos
internos da implementação.
"""

from market_alert.auth.services.services_auth import (
    change_email_service,
    change_password_service,
    confirm_email_verification_service,
    confirm_password_service,
    login_user,
    refresh_token_service,
    request_password_reset_service,
)

__all__ = [
    "login_user",
    "refresh_token_service",
    "confirm_email_verification_service",
    "request_password_reset_service",
    "confirm_password_service",
    "change_password_service",
    "change_email_service",
]
