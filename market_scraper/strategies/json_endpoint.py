""" Estratégias baseadas em endpoints JSON nativos

Este módulo fornece classes de stub para futuras implementações de
scraping que consumam APIs públicas dos marketplaces. As classes atuais
simplesmente retornam {"status": "error"}, permitindo que o fluxo
principal faça fallback automático para estratégias de HTML estático.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlparse

import logging

from market_scraper.utils.intelligent_cache import IntelligentCacheManager
from .base import ScrapingStrategy


# Logger local para registro de eventos de estratégia
logger = logging.getLogger(__name__)

# Gerenciador de cache compartilhado para estratégias JSON (reserva futura)
cache_manager = IntelligentCacheManager()


class JsonEndpointStrategy(ScrapingStrategy):
    """ Estratégia genérica para consumo de endpoints JSON

    Implementação padrão verifica apenas se a URL pertence ao domínio
    esperado e retorna um resultado de erro. As classes concretas devem
    sobrescrever get_data quando houver um endpoint disponível.
    """

    priority = 5
    domain: str = ""

    def supports_url(self, url: str) -> bool:
        """Confere se a URL pertence ao domínio configurado"""
        netloc = urlparse(url).netloc
        return netloc.endswith(self.domain)

    async def get_data(
        self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs: Any
    ) -> dict:
        """Retorna erro indicando que não há implementação disponível"""
        return {"status": "error"}


# ---------- ESTRATÉGIAS COM ENDPOINTS JSON POR MARKETPLACE ---------- #
class MercadoLivreJsonStrategy(JsonEndpointStrategy):
    """Stub para futura coleta via API do Mercado Livre"""
    domain = "mercadolivre.com.br"


class AmazonJsonStrategy(JsonEndpointStrategy):
    """Stub para futura coleta via API da Amazon Brasil"""
    domain = "amazon.com.br"


class MagaluJsonStrategy(JsonEndpointStrategy):
    """Stub para futura coleta via API do Magalu"""
    domain = "magazineluiza.com.br"


# Lista de classes exportadas para facilitar importações diretas
__all__ = [
    "JsonEndpointStrategy",
    "MercadoLivreJsonStrategy",
    "AmazonJsonStrategy",
    "MagaluJsonStrategy",
]

