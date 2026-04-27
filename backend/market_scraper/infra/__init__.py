"""Registro canônico de singletons de infraestrutura do market_scraper.

Expõe os componentes de infraestrutura que residem neste pacote.
Outros singletons do serviço estão em seus módulos canônicos:

    cache           — market_scraper.infra.cache.cache (funções get/set/invalidate)
    playwright_pool — market_scraper.infra.browser.playwright_pool.playwright_pool

Importar diretamente dos módulos acima evita ciclos de dependência.
"""

from __future__ import annotations

from market_scraper.infra.limits.adaptive_rate_limiter import adaptive_rate_limiter


__all__ = [
    "adaptive_rate_limiter",
]
