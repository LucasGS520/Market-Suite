""" Gerenciador de cache inteligente utilizado pelo Market Scraper

O módulo concentra a configuração e a implementação do cache em um único
lugar para simplificar a manutenção. O gerenciamento prioriza o Redis
quando disponível e mantém um dicionário local como contingência, evitando
falhas do pré-pipeline quando a camada de cache estiver indisponível.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import hashlib
import json
import time
import structlog

from market_scraper.core.config_scraper import settings

from shared.utils.logging_utils import sanitize_log_data
from shared.utils.redis_client import get_redis_client


#Valores padrão centralizados para reutilização em todo o módulo
DEFAULT_CACHE_PREFIX = "scraper:product:"
DEFAULT_CACHE_TTL = int(settings.CACHE_BASE_TTL)

#Logger configurado com structlog
logger = structlog.get_logger(__name__)

class IntelligentCacheManager:
    """ Controla leitura e escrita de itens de cache com fallback local """
    def __init__(
        self,
        *,
        prefix: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> None:
        """ Configura o cache com prefixo e TTL definidos em código """
        self.prefix = prefix or DEFAULT_CACHE_PREFIX
        self.ttl = int(ttl) if ttl is not None else DEFAULT_CACHE_TTL
        #Armazenamento local utilizado quando o Redis não está disponível
        self._local_cache: Dict[str, Dict[str, Any]] = {}

    def _hash_content(self, marketplace: str, url: str) -> str:
        """ Gera um hash único combinando marketplace e URL normalizada """
        raw = f"{marketplace}:{url}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _build_key(self, marketplace: str, url: str) -> str:
        """ Monta a chave final usada para armazenar dados no cache """
        return f"{self.prefix}{self._hash_content(marketplace, url)}"

    def get(self, *, marketplace: str | None, url: str) -> Optional[Dict[str, Any]]:
        """ Recupera dados do cache considerando Redis e fallback local """
        marketplace = marketplace or "unknown"
        key = self._build_key(marketplace, url)
        client = get_redis_client()

        if client is not None:
            try:
                data = client.get(key)
                if data:
                    return json.loads(data)
            except Exception as err:
                logger.warning(
                    "falha_cache_redis",
                    erro=sanitize_log_data(str(err)),
                    chave=key,
                )

        entry = self._local_cache.get(key)
        if not entry:
            return None
        
        ttl_entry = entry.get("ttl", self.ttl)
        if time.time() - entry["timestamp"] > ttl_entry:
            self._local_cache.pop(key, None)
            return None
        return entry["value"]

    def set(
        self,
        *,
        marketplace: str | None,
        url: str,
        value: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> None:
        """ Armazena um valor no cache distribuído e no fallback local """
        marketplace = marketplace or "unknown"
        ttl = int(ttl) if ttl is not None else self.ttl
        key = self._build_key(marketplace, url)
        client = get_redis_client()

        if client is not None:
            try:
                client.setex(key, ttl, json.dumps(value))
            except Exception as err:
                logger.warning(
                    "falha_cache_redis",
                    erro=sanitize_log_data(str(err)),
                    chave=key,
                )

        now = time.time()
        entry = self._local_cache.get(key)
        if entry and entry.get("value") == value:
            entry["timestamp"] = now
            entry["ttl"] = ttl
            return
        
        self._local_cache[key] = {"value": value, "timestamp": now, "ttl": ttl}

    def touch(self, *, marketplace: str | None, url: str, ttl: Optional[int] = None) -> None:
        """ Renova o TTL da chave após um acesso bem-sucedido do cache """
        marketplace = marketplace or "unknown"
        key = self._build_key(marketplace, url)
        ttl = int(ttl) if ttl is not None else self.ttl
        client = get_redis_client()

        if client is not None:
            try:
                client.expire(key, ttl)
            except Exception as err:
                logger.warning(
                    "falha_cache_touch",
                    erro=sanitize_log_data(str(err)),
                    chave=key,
                )

        entry = self._local_cache.get(key)
        if entry:
            entry["timestamp"] = time.time()
            entry["ttl"] = ttl
            
__all__ = ["IntelligentCacheManager", "DEFAULT_CACHE_PREFIX", "DEFAULT_CACHE_TTL"]
