"""Ponto único de composição dos serviços de usuários

A exportação explícita reduz acoplamento com arquivos internos e mantém o
contrato público da feature estável para rotas e integrações.
"""

from market_alert.users.services.services_account import (
    change_user_status,
    read_my_profile,
    register_user,
    update_user,
    validate_phone_number,
)
from market_alert.users.services.services_identity import (
    resend_verification,
    verify_email,
    verify_phone_otp,
)
from market_alert.users.services.services_settings import (
    get_notification_settings,
    get_profile_settings,
    get_settings_overview,
    update_notification_settings,
    update_profile_settings,
)

__all__ = [
    "change_user_status",
    "get_notification_settings",
    "get_profile_settings",
    "get_settings_overview",
    "read_my_profile",
    "register_user",
    "resend_verification",
    "update_notification_settings",
    "update_profile_settings",
    "update_user",
    "validate_phone_number",
    "verify_email",
    "verify_phone_otp",
]
