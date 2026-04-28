"""Infraestrutura técnica do market_scraper.

Componentes desta camada:
    robots          — verificação de robots.txt (Redis cache + HTTP + retries)
    cache           — cache condicional, singleflight, TTL
    limits          — rate limiter adaptativo
    logging         — structured logger factory
    errors_map      — taxonomia de erros internos → código HTTP

Regra: esta camada não contém regras de produto — apenas integração técnica.
"""

from __future__ import annotations

from market_scraper.infra.limits.adaptive_rate_limiter import adaptive_rate_limiter


__all__ = [
    "adaptive_rate_limiter",
]
