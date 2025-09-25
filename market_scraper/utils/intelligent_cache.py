""" Gerenciador de cache inteligente com suporte a Redis e fallback local

O utilitário utiliza a configuração carregada em ``market_scraper.utils_controllers.configuration.cache``
para definir prefixo e tempos de vida das chaves. Quando o Redis não está acessível, um armazenamento
em memória é utilizado atomaticamente como contingência, garantindo que o pré-pipeline do scraper
continue operando ser perda de funcionalidade.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional
import hashlib
import json
import time
import structlog

from shared.utils.redis_client import get_redis_client
from shared.utils.logging_utils import sanitize_log_data

if TYPE_CHECKING: #Importação tardia para evitar dependências circulares
    from market_scraper.utils_controllers.configuration.cache import CacheConfig


#Logger configurado com structlog
logger = structlog.get_logger(__name__)

class IntelligentCacheManager:
    """ Cache resiliente que suporta Redis e armazenamento em memória """
    def __init__(
        self,
        *,
        config: "CacheConfig" | None = None,
        prefix: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> None:
        """ Inicializa o gerenciador aplicando a configuração informada
        
        Quando ``config`` não é fornecido, o módulo consulta a instância
        global ``cache_settings`` para obter valores padrão. Os argumentos
        ``prefix`` e ``ttl`` permitem sobreposição pontual durante os testes
        ou cenários específicos.
        """
        if config is None:
            from market_scraper.utils_controllers.configuration import cache_settings
            config = cache_settings.current()

        self._config = config
        self.prefix = prefix or config.prefix
        self.ttl = int(ttl) if ttl is not None else int(config.ttl)
        self._local_cache: Dict[str, Dict[str, Any]] = {}

    def _hash_content(self, marketplace: str, url: str) -> str:
        """ Gera um hash único baseado no marketplace e na URL normalizada """
        raw = f"{marketplace}:{url}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _build_key(self, marketplace: str, url: str) -> str:
        """ Monta a chave final utilizada no cache distribuído/local """
        return f"{self.prefix}{self._hash_content(marketplace, url)}"

    def get(self, *, marketplace: str, url: str) -> Optional[Dict[str, Any]]:
        """ Recupera um valor do cache se ainda estiver válido """
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
        marketplace: str,
        url: str,
        value: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> None:
        """ Armazena um valor no cache distribuído e no fallback local """
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

    def touch(self, *, marketplace: str, url: str, ttl: Optional[int] = None) -> None:
        """ Renova o TTL da chave após um acesso bem-sucedido """
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
            