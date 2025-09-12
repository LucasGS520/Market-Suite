from __future__ import annotations

""" Definições de estratégia de scraping.

Este módulo fornece a classe abstrata ``ScrapingStrategy`` que representa
uma estratégia de coleta de dados. As estratégias concretas devem
informar se suportam a URL desejada e executar a extração dos dados
do produto, retornando ao menos o nome e o preço.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Set


class ScrapingStrategy(ABC):
    """ Estratégia genérica de scraping

    Cada estratégia concreta deve declarar se suporta a URL recebida por
    meio do método :meth:`supports_url` e implementar :meth:`get_data`
    para realizar a coleta. O atributo ``priority`` pode ser utilizado
    futuramente para ordenação de execução.
    """

    priority: int = 100
    dependencies: Set[str] = set()
    # Conjunto de dependências de contexto necessário antes da execução

    @abstractmethod
    def supports_url(self, url: str) -> bool:
        """ Retorna ``True`` se a estratégia consegue lidar com a URL """

    @abstractmethod
    async def get_data(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> dict:
        """ Executa o scraping e retorna os dados relevantes

        Parâmetros adicionais podem ser fornecidos via ``kwargs`` para que
        cada implementação utilize recursos de anti-bloqueio, cache ou
        quaisquer dependências necessárias.
        """

__all__ = ["ScrapingStrategy"]
