"""Facade pública da feature de produtos.

Mantém a API externa da feature enxuta ao expor apenas roteadores HTTP e casos
uso estáveis, reduzindo acoplamento com a estrutura interna dos submódulos.
"""

from market_alert.products.routes import (
    competitors_router,
    dashboard_router,
    monitored_router,
)
from market_alert.products.services import (
    clear_competitors_from_monitored,
    create_competitor_scrape_request,
    create_monitored_product,
    delete_competitor_entry,
    delete_monitored_product_entry,
    gather_dashboard_totals,
    get_monitored_product,
    list_competitors_with_pagination,
    list_featured_monitored_products,
    list_monitored_products,
    update_monitored_pause_state,
)

__all__ = [
    "monitored_router",
    "competitors_router",
    "dashboard_router",
    "create_monitored_product",
    "update_monitored_pause_state",
    "delete_monitored_product_entry",
    "list_monitored_products",
    "list_featured_monitored_products",
    "get_monitored_product",
    "create_competitor_scrape_request",
    "delete_competitor_entry",
    "clear_competitors_from_monitored",
    "list_competitors_with_pagination",
    "gather_dashboard_totals",
]
