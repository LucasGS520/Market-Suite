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
import asyncio

import structlog

from shared.utils.redis_client import get_redis_client

#Logger local para registrar eventos e erros relacionados ao cache
logger = structlog.get_logger(__name__)

#Estrutura interna de cache em memória
_cache: Dict[str, Dict[str, object]] = {}

#Prefixo de chave utilizando no Redis para evitar colisões com outros dados
_CACHE_PREFIX = "scraper:html:"


async def get_cached_html(url: str, max_age: int = 300) -> Optional[str]:
    """ Retorna o HTML em cache de forma assíncrona

    A consulta ao Redis é executada em *thread pool* para não bloquear
    o loop de eventos. Caso o conteúdo não esteja disponível ou seja
    considerado expirado, faz *fallback* para o cache em memória.

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

    #Primeiro tenta recuperar do Redis em executar, caso disponível
    if client is not None:
        try:
            html = await asyncio.to_thread(client.get, key)
            if html:
                return html
        except Exception as err:
            #Se ocorrer qualquer problema com o Redis, usa o cache local
            logger.warning("Falha ao recuperar HTML do Redis", erro=str(err))

    #Fallback para o cache em memória
    entry = _cache.get(url)
    if not entry:
        return None
    if time.time() - entry["timestamp"] > max_age:
        return None
    return entry["html"]

async def set_cached_html(url: str, html: str, ttl: int = 300) -> None:
    """ Armazena o HTML no cache distribuído e local de forma assíncrona

    O conteúdo é salvo no Redis com tempo de expiração ``ttl`` executando a
    operação em *thread pool*. Caso o Redis não esteja acessível, a função
    mantém somente a entrada em memória.

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

    #Atualiza o cache no Redis com tempo de expiração definido em executor
    if client is not None:
        try:
            await asyncio.to_thread(client.setex, key, ttl, html)
        except Exception as err:
            #Caso o Redis falhe, ignora e segue com o cache local
            logger.warning("Falha ao armazenar HTML no Redis", erro=str(err))

    #Sempre armazena no cache local para garantir a reutilização mínima
    _cache[url] = {"html": html, "timestamp": time.time()}
