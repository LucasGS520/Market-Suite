"""Facade estável de casos de uso da feature de produtos.

Expõe explicitamente os submódulos de serviço usados em testes e integrações
para manter previsibilidade nos imports após refactors.
"""

from market_alert.products.services import (
    services_access_control,
    services_competitor_lifecycle,
    services_competitors,
    services_dashboard,
    services_monitored,
    services_monitored_lifecycle,
    services_products,
)

__all__ = [
    "services_access_control",
    "services_competitor_lifecycle",
    "services_competitors",
    "services_dashboard",
    "services_monitored",
    "services_monitored_lifecycle",
    "services_products",
]
