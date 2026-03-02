"""Ponto único de composição dos serviços de usuários

O módulo usa resolução lazy para evitar que imports de bootstrap tragam
services de account/identity antes da hora, o que reduz ciclos no carregamento
inicial de tasks do Celery.
"""

from __future__ import annotations

from importlib import import_module

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

# Mapeia cada símbolo público para o módulo que realmente o implementa.
# A resolução em `__getattr__` mantém o contrato da API estável sem custo de
# import pesado no momento em que o pacote é apenas referenciado.
_EXPORTS_MAP = {
    "change_user_status": "market_alert.users.services.services_account",
    "read_my_profile": "market_alert.users.services.services_account",
    "register_user": "market_alert.users.services.services_account",
    "update_user": "market_alert.users.services.services_account",
    "validate_phone_number": "market_alert.users.services.services_account",
    "resend_verification": "market_alert.users.services.services_identity",
    "verify_email": "market_alert.users.services.services_identity",
    "verify_phone_otp": "market_alert.users.services.services_identity",
    "get_notification_settings": "market_alert.users.services.services_settings",
    "get_profile_settings": "market_alert.users.services.services_settings",
    "get_settings_overview": "market_alert.users.services.services_settings",
    "update_notification_settings": "market_alert.users.services.services_settings",
    "update_profile_settings": "market_alert.users.services.services_settings",
}


def __getattr__(name: str):
    """Resolve exports sob demanda para reduzir acoplamento de importação."""
    module_name = _EXPORTS_MAP.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
