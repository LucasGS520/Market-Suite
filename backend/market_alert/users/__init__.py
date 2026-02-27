"""Facade pública da feature de usuários.

Exporta somente contratos estáveis para consumo externo e composição de rotas.
"""

from market_alert.users.routes import account_router, identity_router, settings_router
from market_alert.users.services import (
    change_user_status,
    get_notification_settings,
    get_profile_settings,
    get_settings_overview,
    read_my_profile,
    register_user,
    resend_verification,
    send_email_verification_message,
    send_phone_otp_message,
    update_notification_settings,
    update_profile_settings,
    update_user,
    validate_phone_number,
    verify_email,
    verify_phone_otp,
)

__all__ = [
    "account_router",
    "identity_router",
    "settings_router",
    "register_user",
    "change_user_status",
    "update_user",
    "read_my_profile",
    "validate_phone_number",
    "resend_verification",
    "verify_email",
    "verify_phone_otp",
    "send_email_verification_message",
    "send_phone_otp_message",
    "get_settings_overview",
    "get_profile_settings",
    "update_profile_settings",
    "get_notification_settings",
    "update_notification_settings",
]
