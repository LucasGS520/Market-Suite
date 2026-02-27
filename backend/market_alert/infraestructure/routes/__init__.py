""" Rotas técnicas da camada de infraestrutura 

Este módulo concentra os roteadores HTTP usados para saúde e prontidão,
evitando que consumidores dependam de caminhos internos de arquivo.
"""

from market_alert.infraestructure.routes.routes_health import router as health_router

__all__ = ["health_router"]
