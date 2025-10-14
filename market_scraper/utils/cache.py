""" Gerencia cache do scraper com adapters configuráveis e métricas

O módulo mantém a API pública ``get``/``set``/``invalidate``/``clear``
para o restante do pipeline enquanto delega a lógica de armazenamento
para adapters específicos. O backend padrão usa ``cachetools.TTLCache``
com controle de LRU, contabiliza hits/misses/evictions e atualiza as
métricas expostas para observabilidade. Quando configurado, um adapter
Redis fornece persistência compartilhada com conexão via pool, métricas
de erro e chaves sanitizadas, preservando compatibilidade.
"""

from __future__ import annotations

import threading
import time

import hashlib
from typing import Callable, Optional, Protocol

import redis
from redis.exceptions import RedisError
import structlog
from cachetools import Cache, TTLCache

from market_scraper.core.config_scraper import settings
from shared.metrics.metrics_scraper import (
    SCRAPER_CACHE_EVICTIONS_TOTAL,
    SCRAPER_CACHE_HIT_RATE,
    SCRAPER_CACHE_LOOKUPS_TOTAL,
    SCRAPER_CACHE_REDIS_ERRORS_TOTAL,
    SCRAPER_CACHE_SIZE,
)


logger = structlog.get_logger(__name__)

class CacheAdapter(Protocol):
    """ Define interface mínima para adapters de cache do scraper """
    def get(self, url: str) -> Optional[str]:
        """ Recupera HTML armazenado ou ``None`` se não houver entrada """

    def set(self, url: str, html: str, ttl_seconds: int) -> None:
        """ Salva HTML associado à URL respeitando o TTL informado """
        
    def invalidate(self, url: str) -> None:
        """ Remove entrada específica caso exista no backend """

    def clear(self) -> None:
        """ Limpa todas as entradas do backend de cache """

class _InstrumentedTTLCache(TTLCache):
    """ Estende ``TTLCache`` para registrar remoções e TTL por item """
    def __init__(self, maxsize: int, ttl: int) -> None:
        super().__init__(maxsize=maxsize, ttl=ttl, timer=time.monotonic)
        self._on_enviction: Optional[Callable[[int, str], None]] = None

    def configure_eviction_callback(self, callback: Callable[[int, str], None]) -> None:
        """ Define função de callback para acompanhar remoções do cache """
        self._on_enviction = callback

    def expire(self, time: Optional[float] = None):
        """ Remove itens expirados notificando o callback configurado """
        expired = super().expire(time)
        if expired and self._on_enviction is not None:
            self._on_enviction(len(expired), "expired")
        return expired
    
    def popitem(self):
        """ Remove item LRU e registra eviction por capacidade """
        item = super().popitem()
        if self._on_enviction is not None:
            self._on_enviction(1, "capacity")
        return item
    
    def set_with_ttl(self, key: str, value: str, ttl_seconds: int) -> None:
        """ Replica ``__setitem__`` permitindo TTL individual por chave """
        ttl_seconds = max(ttl_seconds, 0)
        with self.timer as current_time:
            expired = super().expire(current_time)
            if expired and self._on_enviction is not None:
                self._on_enviction(len(expired), "expired")
            Cache.__setitem__(self, key, value)
        try:
            link = self._TTLCache__getlink(key)
        except KeyError:
            links = self._TTLCache__links
            link = TTLCache._Link(key)
            links[key] = link
        else:
            link.unlink()
        root = self._TTLCache__root
        prev = root.prev
        link.expires = current_time + ttl_seconds
        link.next = root
        link.prev = prev
        prev.next = root.prev = link

class InMemoryTTLCacheAdapter:
    """ Adapter em memória com LRU/TTL e instrumentação de métricas """
    def __init__(self, max_entries: int, default_ttl_seconds: int) -> None:
        self._cache = _InstrumentedTTLCache(max_entries, default_ttl_seconds)
        self._cache.configure_eviction_callback(self._record_eviction)
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        SCRAPER_CACHE_SIZE.set(0)
        SCRAPER_CACHE_HIT_RATE.set(0)

    def _record_eviction(self, count: int, reason: str) -> None:
        """ Atualiza contadores quando itens são removidos do cache """
        SCRAPER_CACHE_EVICTIONS_TOTAL.labels(reason=reason).inc(count)
        SCRAPER_CACHE_SIZE.set(len(self._cache))

    def _update_hit_rate(self) -> None:
        """ Recalcula gauge de taxa de acerto com base em hits e misses """
        total = self._hits + self._misses
        rate = (self._hits / total) if total else 0.0
        SCRAPER_CACHE_HIT_RATE.set(rate)

    def get(self, url: str) -> Optional[str]:
        """ Busca HTML armazenado registrando métricas de hit/miss """
        with self._lock:
            expired = self._cache.expire()
            if expired:
                SCRAPER_CACHE_SIZE.set(len(self._cache))
            try:
                value = self._cache[url]
            except KeyError:
                self._misses += 1
                SCRAPER_CACHE_LOOKUPS_TOTAL.labels(outcome="miss").inc()
                self._update_hit_rate()
                return None
            else:
                self._hits += 1
                SCRAPER_CACHE_LOOKUPS_TOTAL.labels(outcome="hit").inc()
                self._update_hit_rate()
                return value
        
    def set(self, url: str, html: str, ttl_seconds: int) -> None:
        """ Armazena HTML respeitando TTL informado e política LRU """
        with self._lock:
            self._cache.set_with_ttl(url, html, ttl_seconds)
            SCRAPER_CACHE_SIZE.set(len(self._cache))

    def invalidate(self, url: str) -> None:
        """ Remove entrada específica do cache em memória """
        with self._lock:
            removed = self._cache.pop(url, None)
            if removed is not None:
                SCRAPER_CACHE_SIZE.set(len(self._cache))

    def clear(self) -> None:
        """ Limpa completamente o cache em memória para manutenção """
        with self._lock:
            self._cache.clear()
            SCRAPER_CACHE_SIZE.set(0)

class RedisCacheAdapter:
    """ Adapter Redis com TTL individual, métricas e chaves sanitizadas """
    def __init__(self, redis_url: str, namespace: str = "scraper:cache") -> None:
        self._namespace = namespace.rstrip(":")
        self._index_key = f"{self._namespace}:index"
        self._pool = redis.ConnectionPool.from_url(
            redis_url,
            decode_responses=True,
        )
        self._hits = 0
        self._misses = 0
        self._lock = threading.RLock()
        SCRAPER_CACHE_SIZE.set(0)

    def _client(self) -> redis.Redis:
        """ Obtém cliente Redis associado ao pool compartilhado """
        return redis.Redis(connection_pool=self._pool)
    
    def _encode_key(self, url: str) -> str:
        """ Converte URL em chave com hash para evitar vazamento de dados """
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return f"{self._namespace}:item:{digest}"
    
    def _update_hit_rate(self) -> None:
        """ Atualiza gauge de taxa de acerto com base em hits/misses locais """
        with self._lock:
            total = self._hits + self._misses
            rate = (self._hits / total) if total else 0.0
            SCRAPER_CACHE_HIT_RATE.set(rate)

    def _register_hit(self) -> None:
        """ Incrementa contadores de acerto e ajusta métricas """
        with self._lock:
            self._hits += 1
        SCRAPER_CACHE_LOOKUPS_TOTAL.labels(outcome="hit").inc()
        self._update_hit_rate()

    def _register_miss(self) -> None:
        """ Incrementa contadores de miss e ajusta métricas """
        with self._lock:
            self._misses += 1
        SCRAPER_CACHE_LOOKUPS_TOTAL.labels(outcome="miss").inc()
        self._update_hit_rate()

    def _record_error(self, operation: str, exc: Exception, key: Optional[str] = None) -> None:
        """ Consolida erros de backend registrando métrica e log estruturado """
        SCRAPER_CACHE_REDIS_ERRORS_TOTAL.labels(operation=operation).inc()
        logger.warning(
            "redis_cache_operation_error",
            operation=operation,
            key=key,
            error=str(exc),
        )

    def _update_size(self, client: redis.Redis) -> None:
        """ Atualiza gauge de tamanho usando cardinalidade do índice """
        try:
            size = client.scard(self._index_key)
        except RedisError as exc:
            self._record_error("scard", exc)
        else:
            SCRAPER_CACHE_SIZE.set(size)

    def get(self, url: str) -> Optional[str]:
        """ Busca HTML no Redis atualizando métricas e índice auxiliar """
        key = self._encode_key(url)
        client = self._client()
        try:
            value = client.get(key)
        except RedisError as exc:
            self._record_error("get", exc, key=key)
            return None
        
        if value is None:
            try:
                client.srem(self._index_key, key)
            except RedisError as exc:
                self._record_error("srem", exc, key=key)
            else:
                self._update_size(client)
            self._register_miss()
            return None
        
        self._register_hit()
        return value
    
    def set(self, url: str, html: str, ttl_seconds: int) -> None:
        """ Armazena HTML com TTL definido e mantém índice cardinal """
        ttl_seconds = max(int(ttl_seconds), 0)
        key = self._encode_key(url)
        client = self._client()

        if ttl_seconds == 0:
            self.invalidate(url)
            return
        
        try:
            pipe = client.pipeline()
            pipe.set(key, html, ex=ttl_seconds)
            pipe.sadd(self._index_key, key)
            pipe.execute()
        except RedisError as exc:
            self._record_error("set", exc, key=key)
            return
    
        self._update_size(client)

    def invalidate(self, url: str) -> None:
        """ Remove entrada específica do cache Redis e atualiza índice """
        key = self._encode_key(url)
        client = self._client()
        try:
            client.delete(key)
            client.srem(self._index_key, key)
        except RedisError as exc:
            self._record_error("delete", exc, key=key)
            return
        
        self._update_size(client)

    def clear(self) -> None:
        """ Limpa completamente chaves gerenciadas pelo namespace atual """
        client = self._client()
        try:
            members = client.smembers(self._index_key)
        except RedisError as exc:
            self._record_error("smembers", exc)
            return
        
        if members:
            try:
                client.delete(*members)
            except RedisError as exc:
                self._record_error("delete", exc)
                #Continua para apagar índice mesmo que parte falhe

        try:
            client.delete(self._index_key)
        except RedisError as exc:
            self._record_error("delete_index", exc)
            return
        
        SCRAPER_CACHE_SIZE.set(0)

def _build_cache_adapter() -> CacheAdapter:
    """ Retorna adapater configurado via environment mantendo compatibilidade """
    backend = settings.SCRAPER_CACHE_BACKEND.lower()
    if backend == "memory":
        return InMemoryTTLCacheAdapter(
            max_entries=settings.SCRAPER_CACHE_MAX_ENTRIES,
            default_ttl_seconds=settings.SCRAPER_CACHE_TTL_SECONDS,
        )
    if backend == "redis":
        return RedisCacheAdapter(settings.redis_url)
    raise ValueError(f"Backend de cache '{backend}' não suportado nesta etapa")

_CACHE_ADAPTER = _build_cache_adapter()

def get(url: str) -> Optional[str]:
    """ Consulta cache configurado para obter HTML previamente armazenado """
    return _CACHE_ADAPTER.get(url)

def set(url: str, html: str, ttl_seconds: int) -> None:
    """ Armazena HTML da URL mantendo compatibilidade da API pública """
    _CACHE_ADAPTER.set(url, html, ttl_seconds)

def invalidate(url: str) -> None:
    """ Remove uma única entrada armazenada para a URL informada """
    _CACHE_ADAPTER.invalidate(url)

def clear() -> None:
    """ Apaga todas as entradas existentes do backend de cache atual """
    _CACHE_ADAPTER.clear()


__all__ = [
    "get",
    "set",
    "invalidate",
    "clear",
]
