"""Pacote raiz do serviço ``market_alert``.

Este módulo expõe apenas as features públicas de primeiro nível para manter
um contrato de importação estável e fácil de entender.
"""

from market_alert import (
    auth,
    collectors,
    comparisons,
    core,
    enums,
    infraestructure,
    models,
    notifications,
    products,
    schemas,
    users,
)

# Mantém explícita a superfície pública suportada do pacote.
__all__ = [
    "auth",
    "collectors",
    "comparisons",
    "core",
    "enums",
    "infraestructure",
    "models",
    "notifications",
    "products",
    "schemas",
    "users",
]
