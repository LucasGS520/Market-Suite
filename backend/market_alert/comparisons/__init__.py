""" Facade pública da feature de comparações de preços.

Expõe explicitamente os subpacotes estáveis usados por rotas e orquestração,
sem obrigar consumidores a conhecer caminhos internos.
"""

from market_alert.comparisons import crud, domain, routes, services, tasks, utils

__all__ = ["crud", "domain", "routes", "services", "tasks", "utils"]
