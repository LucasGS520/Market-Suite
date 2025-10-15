""" Gerencia o cache em memória do scraper com LRU/TTL e métricas

O módulo mantém a API pública ``get``/``set``/``invalidate``/``clear``
para o restante do pipeline enquanto encapsula ``cachetools.TTLCache``
com controles adicionais de métricas. Implementações alternativas foram
retiradas para simplificar operação: toda execução usa o backend em
memória documentado.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from cachetools import Cache, TTLCache

from market_scraper.core.config_scraper import settings
from shared.metrics.metrics_scraper import (
    SCRAPER_CACHE_EVICTIONS_TOTAL,
    SCRAPER_CACHE_HIT_RATE,
    SCRAPER_CACHE_LOOKUPS_TOTAL,
    SCRAPER_CACHE_SIZE,
)

class _InstrumentedTTLCache(TTLCache):
    """ Estende ``TTLCache`` para registrar remoções e TTL por item """
    def __init__(self, maxsize: int, ttl: int) -> None:
        super().__init__(maxsize=maxsize, ttl=ttl, timer=time.monotonic)
        self._on_eviction: Optional[Callable[[int, str], None]] = None

    def configure_eviction_callback(self, callback: Callable[[int, str], None]) -> None:
        """ Associa callback invocado sempre que ocorrer uma remoção """
        self._on_eviction = callback

    def expire(self, time: Optional[float] = None):
        """ Remove itens expirados notificando o callback configurado """
        expired = super().expire(time)
        if expired and self._on_eviction is not None:
            self._on_eviction(len(expired), "expired")
        return expired
    
    def popitem(self):
        """ Remove item LRU e registra eviction por capacidade """
        item = super().popitem()
        if self._on_eviction is not None:
            self._on_eviction(1, "capacity")
        return item
    
    def set_with_ttl(self, key: str, value: str, ttl_seconds: int) -> None:
        """ Replica ``__setitem__`` permitindo TTL individual por chave """
        ttl_seconds = max(ttl_seconds, 0)
        current_time = self.timer()
        #Evita tratar ``timer`` como context manager, pois é função simples
        expired = super().expire(current_time)
        if expired and self._on_eviction is not None:
            self._on_eviction(len(expired), "expired")
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

_CACHE_ADAPTER = InMemoryTTLCacheAdapter(
    max_entries=settings.SCRAPER_CACHE_MAX_ENTRIES,
    default_ttl_seconds=settings.SCRAPER_CACHE_TTL_SECONDS,
)

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
