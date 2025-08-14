""" Utilidades de cache distribuído para o scraper

Este módulo implementa um cache simples utilizando Redis para
armazenar o HTML obtido durante o scraping. Ao reutilizar conteúdos
recentes, evita requisições desnecessárias aos sites externos.
Também é mantido um cache em memória como *fallback* caso o Redis
esteja indisponível
"""

from __future__ import annotations

from typing import Optional, Dict
import time

from shared.utils.redis_client import get_redis_client

#Estrutura interna de cache em memória
_cache: Dict[str, Dict[str, object]] = {}

#Prefixo de chave utilizando no Redis para evitar colisões com outros dados
_CACHE_PREFIX = "scraper:html:"


def get_cached_html(url: str, max_age: int = 300) -> Optional[str]:
    """ Retorna o HTML em cache caso ainda esteja válido e disponível

    Parâmetros
    ----------
    url:
        Endereço do recurso solicitado
    max_age:
        Tempo máximo, em segundos, para que o conteúdo seja considerado válido

    Retorno
    -------
    str ou ``None``
        Conteúdo HTML previamente armazenado ou ``None`` se
        não houver cache utilizável
    """
    client = get_redis_client()
    #Monta a chave com o prefixo padronizado e a URL solicitada
    key = f"{_CACHE_PREFIX}{url}"

    #Primeiro tenta recuperar do Redis
    try:
        html = client.get(key)
        if html:
            return html
    except Exception:
        #Se ocorrer qualquer problema com o Redis, usa o cache local
        pass

    #Fallback para o cache em memória
    entry = _cache.get(url)
    if not entry:
        return None
    if time.time() - entry["timestamp"] > max_age:
        return None
    return entry["html"]

def set_cached_html(url: str, html: str, ttl: int = 300) -> None:
    """ Armazena o HTML no cache distribuído e local

    O conteúdo é salvo no Redis com tempo de expiração ``ttl``.
    Se o Redis não estiver acessível, a função mantém somente
    a entrada em memória.

    Parâmetros
    ----------
    url:
        Endereço do recurso obtido
    html:
        Conteúdo HTML retornado pelo scraper
    ttl:
        Tempo, em segundos, para expiração da chave no Redis
    """

    client = get_redis_client()
    #Combina o prefixo de cache com a URL alvo
    key = f"{_CACHE_PREFIX}{url}"

    #Atualiza o cache no Redis com tempo de expiração definido
    try:
        client.setex(key, ttl, html)
    except Exception:
        pass #Caso o Redis falhe, ignora e segue com o cache local

    #Sempre armazena no cache local para garantir a reutilização mínima
    _cache[url] = {"html": html, "timestamp": time.time()}
