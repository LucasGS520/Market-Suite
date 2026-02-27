"""Camada core do ``market_alert``.

Este módulo centraliza os imports mais usados da camada ``core`` para
oferecer uma API estável e simples para os demais submódulos do serviço.
"""

from market_alert.core.config_alert import Settings, settings
from market_alert.core.jwt import create_access_token, verify_access_token
from market_alert.core.password import hash_password, verify_password
from market_alert.core.tokens import (
    generate_phone_otp,
    generate_reset_token,
    generate_verification_token,
    hash_token,
    token_expiry,
)

# A lista explícita evita exportações acidentais e documenta a API suportada.
__all__ = [
    "Settings",
    "settings",
    "create_access_token",
    "verify_access_token",
    "hash_password",
    "verify_password",
    "generate_phone_otp",
    "generate_reset_token",
    "generate_verification_token",
    "hash_token",
    "token_expiry",
]
