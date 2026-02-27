"""Facade estável de casos de uso da feature de produtos.

A intenção é centralizar importações públicas para que consumidores externos
não dependam da organização interna dos submódulos.
"""

from market_alert.products.services.services_competitor_lifecycle import (
    clear_competitors_from_monitored,
    create_competitor_scrape_request,
    delete_competitor_entry,
)
from market_alert.products.services.services_competitors import (
    list_competitors_with_pagination,
)
from market_alert.products.services.services_dashboard import gather_dashboard_totals
from market_alert.products.services.services_monitored import (
    get_monitored_product,
    list_featured_monitored_products,
    list_monitored_products,
)
from market_alert.products.services.services_monitored_lifecycle import (
    create_monitored_product,
    delete_monitored_product_entry,
    update_monitored_pause_state,
)

__all__ = [
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
