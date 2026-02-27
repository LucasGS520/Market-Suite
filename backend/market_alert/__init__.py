"""Pacote raiz do serviço ``market_alert``.

Este ponto de entrada centraliza as features públicas da aplicação para que
consumidores externos importem apenas contratos estáveis.
"""

from market_alert import auth, collectors, comparisons, core, enums, notifications, products, schemas, users

# Mantém explícitos os módulos públicos de primeiro nível para reduzir
# acoplamento com a estrutura interna de pastas.
__all__ = [
    "auth",
    "collectors",
    "comparisons",
    "core",
    "enums",
    "notifications",
    "products",
    "schemas",
    "users",
]
