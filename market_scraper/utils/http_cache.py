""" Utilitários de cache para requisições HTTP

Fornece funções para armazenar e recuperar cabeçalhos ``ETag`` e
``Last-Modified`` de cada URL usando Redis. Também disponibiliza a classe
:class:`ContentSignature` responsável por calcular e persistir um hash
``sha256`` do conteúdo HTML, permitindo detectar quando uma página não
sofreu alterações entre duas requisições.
"""

from __future__ import annotations

import hashlib
from typing import Dict, Optional

from shared.utils import redis_client


#Prefixos padronizados para as chaves no Redis
_ETAG_PREFIX = "http_cache:etag:"
_LAST_MODIFIED_PREFIX = "http_cache:last_modified:"
_SIGNATURE_PREFIX = "http_cache:signature:"

def _hash_url(url: str) -> str:
    """ Gera um hash único para a URL usando ``sha256`` """
    return hashlib.sha256(url.encode("utf-8")).hexdigest()

def store_cache_headers(
    url: str,
    *,
    etag: Optional[str] = None,
    last_modified: Optional[str] = None
) -> None:
    """ Armazena os cabeçalhos ``ETag`` e ``Last_Modified`` associados à URL

    Caso o cliente Redis não esteja disponível, a função retorna sem gerar
    exceções, garantindo que a ausência de cache não interrompa o fluxo
    principal de scraping.
    """

    client = redis_client.get_redis_client()
    if client is None:
        return

    url_hash = _hash_url(url)
    if etag is not None:
        client.set(f"{_ETAG_PREFIX}{url_hash}", etag)
    if last_modified is not None:
        client.set(f"{_LAST_MODIFIED_PREFIX}{url_hash}", last_modified)

def get_cache_headers(url: str) -> Dict[str, Optional[str]]:
    """ Recupera os valores de ``ETag`` e ``Last-Modified`` para a URL

    Retorna sempre um dicionário contendo as chaves ``ETag`` e
    ``last_modified``. Quando não houver dados ou o Redis estiver
    indisponível, os valores serão ``None``.
    """

    client = redis_client.get_redis_client()
    if client is None:
        return {"etag": None, "last_modified": None}

    url_hash = _hash_url(url)
    etag = client.get(f"{_ETAG_PREFIX}{url_hash}")
    last_modified = client.get(f"{_LAST_MODIFIED_PREFIX}{url_hash}")
    return {"etag": etag, "last_modified": last_modified}

class ContentSignature:
    """ Gerencia a assinatura de conteúdo HTML de uma URL """
    def __init__(self, url: str):
        self.url = url

    def _key(self) -> str:
        """ Monta a chave exclusiva utilizada no Redis """
        return f"{_SIGNATURE_PREFIX}{_hash_url(self.url)}"

    def calculate(self, html: str) -> str:
        """ Calcula o hash ``sha256`` para o conteúdo HTML informado """
        return hashlib.sha256(html.encode("utf-8")).hexdigest()

    def get(self) -> Optional[str]:
        """ Obtém a assinatura atual armazenada para a URL """
        client = redis_client.get_redis_client()
        if client is None:
            return None
        return client.get(self._key())

    def update(self, html: str) -> str:
        """ Calcula a armazena a assinatura para o HTML fornecido """
        signature = self.calculate(html)
        client = redis_client.get_redis_client()
        if client is not None:
            client.set(self._key(), signature)
        return signature

    def has_changed(self, html: str) -> bool:
        """ Verifica se o HTML mudou em relação ao valor armazenado

        A primeira chamada sempre irá armazenar o hash do conteúdo e
        retornar ``True``. Nas chamadas subsequentes, se o hash calculado
        for idêntico ao anterior, retorna ``False`` indicando que o
        conteúdo não sofreu alterações
        """
        client = redis_client.get_redis_client()
        if client is None:
            return True

        key = self._key()
        new_signature = self.calculate(html)
        old_signature = client.get(key)
        if old_signature == new_signature:
            return False
        client.set(key, new_signature)
        return True
