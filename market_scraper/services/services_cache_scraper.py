""" Utilidades simples de cache para scraper

Este módulo fornece funções básicas para reutilizar HTML obtido
anteriormente e evitar requisições desnecessárias.
As implementações são propositalmente enxutas para funcionar como
um placeholder até que um cache mais robusto seja adicionado.
"""

from __future__ import annotations

from typing import Optional, Dict
import time

#Estrutura interna de cache em memória. Chaves são URLs e valores contêm o HTML e o instante de armazenamento
_cache: Dict[str, Dict[str, object]] = {}


def use_cache_if_not_modified(url: str, max_age: int = 300) -> Optional[str]:
    """ Retorna o HTML em cache caso ainda esteja válido

    Parâmetros
    ----------
    url:
        Endereço do recurso solicitado
    max_age:
        Tempo máximo, em segundos, para que o conteúdo seja considerado válido

    Retorno
    -------
    str ou ``None``
        Conteúdo HTML previamente armazenado ou ``None`` se o
        cache não puder ser utilizado
    """

    entry = _cache.get(url)
    if not entry:
        return None
    if time.time() - entry["timestamp"] > max_age:
        return None
    return entry["html"]

def update_cache(url: str, html: str) -> None:
    """ Atualiza o cache com o HTML mais recente

    Parâmetros
    ----------
    url:
        Endereço do recurso obtido
    html:
        Conteúdo HTML retornado pelo scraper
    """
    _cache[url] = {"html": html, "timestamp": time.time()}
