""" Exporta roteadores HTTP do domínio de produtos """

from market_alert.products.routes.routes_monitored import router as monitored_router
from market_alert.products.routes.routes_competitors import router as competitors_router

__all__ = ["monitored_router", "competitors_router"]
