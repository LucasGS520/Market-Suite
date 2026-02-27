""" Facade de roteadores HTTP da feature de produtos.

Manter os imports públicos aqui evita dependência direta de arquivos internos
como ``routes_monitored`` e ``routes_competitors``.
"""

from market_alert.products.routes.routes_monitored import router as monitored_router
from market_alert.products.routes.routes_competitors import router as competitors_router
from market_alert.products.routes.routes_dashboard import router as dashboard_router


__all__ = ["monitored_router", "competitors_router", "dashboard_router"]
