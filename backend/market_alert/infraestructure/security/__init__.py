"""Componentes de segurança ligados à infraestrutura.

Este pacote implementa integrações com FastAPI/Redis necessárias para
autenticação, autorização e proteção operacional.
"""

from market_alert.infraestructure.security.auth_context import (
    get_current_admin_user,
    get_current_user,
)
from market_alert.infraestructure.security.bruteforce import (
    block_ip,
    enforce_rate_limit,
    record_failed_attempt,
    reset_failed_attempts,
)

__all__ = [
    "get_current_user",
    "get_current_admin_user",
    "enforce_rate_limit",
    "record_failed_attempt",
    "reset_failed_attempts",
    "block_ip",
]
