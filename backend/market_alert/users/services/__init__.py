"""Ponto único de composição dos serviços de usuários."""

from market_alert.users.services.services_account import (
    change_user_status,
    read_my_profile,
    register_user,
    update_user,
    validate_phone_number,
)
from market_alert.users.services.services_delivery import (
    send_email_verification_message,
    send_phone_otp_message,
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
    "read_my_profile",
    "register_user",
    "resend_verification",
    "send_email_verification_message",
    "send_phone_otp_message",
    "update_user",
    "validate_phone_number",
    "verify_email",
    "verify_phone_otp",
    "get_notification_settings",
    "get_profile_settings",
    "get_settings_overview",
    "update_notification_settings",
    "update_profile_settings",
]