""" Gerenciador de cache inteligente para resultados de scraping

Este módulo provê a classe :class:`IntelligentCacheManager` que utiliza
Redis (quando disponível) e um cache em memória como *fallback*. As chaves
são geradas levando em conta o marketplace, evitando que diferentes sites
compartilhem o mesmo espaço de cache.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import hashlib
import json
import time
import structlog

from shared.utils.redis_client import get_redis_client


#Logger configurado com structlog
logger = structlog.get_logger(__name__)

class IntelligentCacheManager:
    """ Cache simples com isolamento por marketplace """
    def __init__(self, prefix: str = "scraper:product:", ttl: int = 300) -> None:
        """ Inicializa o gerenciador de cache

        Paramêtros
        ----------
        prefix:
            Prefixo utilizado nas chaves do Redis.
        ttl:
            Tempo de expiração padrão em segundos.
        """
        self.prefix = prefix
        self.ttl = ttl
        self._local_cache: Dict[str, Dict[str, Any]] = {}

    def _hash_content(self, marketplace: str, url: str) -> str:
        """ Gera um hash único baseado no marketplace e na URL """
        raw = f"{marketplace}:{url}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _build_key(self, marketplace: str, url: str) -> str:
        """ Monta a chave final utilizada no cache """
        return f"{self.prefix}{self._hash_content(marketplace, url)}"

    def get(self, *, marketplace: str, url: str) -> Optional[Dict[str, Any]]:
        """ Recupera um valor do cache se ainda estiver válido

        Caso o Redis não esteja acessível ou a chave tenha expirado,
        a busca recorre ao cache local em memória.
        """
        key = self._build_key(marketplace, url)
        client = get_redis_client()

        if client is not None:
            try:
                data = client.get(key)
                if data:
                    return json.loads(data)
            except Exception as err:
                logger.warning("falha_cache_redis", erro=str(err))

        entry = self._local_cache.get(key)
        if not entry:
            return None
        if time.time() - entry["timestamp"] > self.ttl:
            return None
        return entry["value"]

    def set(self, *, marketplace: str, url: str, value: Dict[str, Any], ttl: Optional[int] = None) -> None:
        """ Armazena um valor no cache distribuído e local

        O dado é serializado em JSON para facilitar o compartilhamento
        entre processos e linguagens.
        """
        ttl = ttl or self.ttl
        key = self._build_key(marketplace, url)
        client = get_redis_client()

        if client is not None:
            try:
                client.setex(key, ttl, json.dumps(value))
            except Exception as err:
                logger.warning("falha_cache_redis", erro=str(err))

        self._local_cache[key] = {"value": value, "timestamp": time.time()}
