from __future__ import annotations

""" Definições de estratégia de scraping.

Este módulo oferece a classe base ``ScrapingStrategy`` e utilidades 
para registrar e selecionar estratégias concretas.
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional


class ScrapingStrategy(ABC):
    """ Estratégia genérica de scraping

    Cada estratégia deve informar se suporta a url recebida
    e executar a coleta retornando ao menos o nome e o preço do produto.
    """

    priority: int = 100

    @abstractmethod
    def supports_url(self, url: str) -> bool:
        """ Retorna True se a estratégia consegue lidar com a URL """

    @abstractmethod
    async def get_data(
        self,
        *,
        url: str,
        user_id: Any,
        payload: Any,
        product_type: str,
        rate_limiter: Any | None = None,
        circuit_breaker: Any | None = None,
        recovery_manager: Any | None = None,
    ) -> dict:
        """ Executa o scraping e retorna os dados relevantes """

_STRATEGIES: List[ScrapingStrategy] = []


def register_strategy(strategy: ScrapingStrategy) -> None:
    """ Registra uma nova estratégia no repositório interno """
    _STRATEGIES.append(strategy)
    _STRATEGIES.sort(key=lambda s: s.priority)

def get_strategy_for_url(url: str) -> Optional[ScrapingStrategy]:
    """ Retorna a primeira estratégia compatível com a url informada """
    for strategy in _STRATEGIES:
        if strategy.supports_url(url):
            return strategy
    return None
