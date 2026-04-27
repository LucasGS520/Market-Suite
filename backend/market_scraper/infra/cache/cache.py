""" Gerencia o cache em memória do scraper com LRU/TTL

O módulo mantém a API pública ``get``/``set``/``invalidate``/``clear``
para o restante do pipeline enquanto encapsula ``cachetools.TTLCache``
com controles adicionais de expiração. Implementações alternativas foram
retiradas para simplificar operação: toda execução usa o backend em
memória documentado.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

from cachetools import Cache, TTLCache
import structlog

from market_scraper.core.config_scraper import settings


class _InstrumentedTTLCache(TTLCache):
    """ Estende ``TTLCache`` para registrar remoções e TTL por item """
    def __init__(self, maxsize: int, ttl: int) -> None:
        super().__init__(maxsize=maxsize, ttl=ttl, timer=time.monotonic)
        self._on_eviction: Optional[Callable[[int, str], None]] = None
        #Marca se o fallback já foi sinalizado para evitar logs repetitivos
        self._fallback_warning_emitted = False

    def configure_eviction_callback(self, callback: Callable[[int, str], None]) -> None:
        """ Associa callback invocado sempre que ocorrer uma remoção """
        self._on_eviction = callback

    def expire(self, time: Optional[float] = None) -> int:
        """ Remove itens expirados notificando o callback configurado """
        before = Cache.__len__(self)
        super().expire(time)
        removed = before - Cache.__len__(self)
        if removed > 0 and self._on_eviction is not None:
            self._on_eviction(removed, "expired")
        return removed
    
    def popitem(self):
        """ Remove item LRU e registra eviction por capacidade """
        item = super().popitem()
        if self._on_eviction is not None:
            self._on_eviction(1, "capacity")
        return item
    
    def set_with_ttl(self, key: str, value: Any, ttl_seconds: int) -> int:
        """ Replica ``__setitem__`` permitindo TTL individual e retorna expirados """
        ttl_seconds = max(ttl_seconds, 0)
        current_time = self.timer()
        #Evita tratar ``time`` como context manager, função simples
        before = Cache.__len__(self)
        super().expire(current_time)
        removed = before - Cache.__len__(self)
        if removed > 0 and self._on_eviction is not None:
            self._on_eviction(removed, "expired")
        Cache.__setitem__(self, key, value)
        #Ajusta manualmente o link para suportar TTL customizado, cai para comportamento padrão se API interna de cachetools mudar
        try:
            link = self._TTLCache__getlink(key)
        except KeyError:
            try:
                links = self._TTLCache__links
            except AttributeError as error:
                self._log_private_api_warning(error)
                return removed
            link = TTLCache._Link(key)
            links[key] = link
        except AttributeError as error:
            self._log_private_api_warning(error)
            return removed
        else:
            link.unlink()
        try:
            root = self._TTLCache__root
        except AttributeError as error:
            self._log_private_api_warning(error)
            return removed
        try:
            prev = root.prev
            link.expires = current_time + ttl_seconds
            link.next = root
            link.prev = prev
            prev.next = root.prev = link
        except Exception as error:
            self._log_private_api_warning(error)
            return removed
        return removed
    
    def _log_private_api_warning(self, error: Exception) -> None:
        """ Notifica que o cachetools mudou a API interna e ativa fallback padrão """
        if not self._fallback_warning_emitted:
            structlog.get_logger(__name__).warning(
                "cachetools_private_api_unavailable",
                error=str(error),
            )
            self._fallback_warning_emitted = True

class InMemoryTTLCacheAdapter:
    """ Adapter em memória com LRU/TTL e expiração configurável """
    def __init__(self, max_entries: int, default_ttl_seconds: int) -> None:
        self._cache = _InstrumentedTTLCache(max_entries, default_ttl_seconds)
        self._lock = threading.RLock()

    def get(self, url: str) -> Optional[Any]:
        """ Busca conteudo armazenado preservando a política LRU/TTL """
        with self._lock:
            self._cache.expire()
            try:
                value = self._cache[url]
            except KeyError:
                return None
            else:
                return value
        
    def set(self, url: str, value: Any, ttl_seconds: int) -> None:
        """ Armazena valores respeitando TTL informado e política LRU """
        with self._lock:
            self._cache.set_with_ttl(url, value, ttl_seconds)

    def invalidate(self, url: str) -> None:
        """ Remove entrada específica do cache em memória """
        with self._lock:
            self._cache.pop(url, None)

    def clear(self) -> None:
        """ Limpa completamente o cache em memória para manutenção """
        with self._lock:
            self._cache.clear()

_CACHE_ADAPTER = InMemoryTTLCacheAdapter(
    max_entries=settings.SCRAPER_CACHE_MAX_ENTRIES,
    default_ttl_seconds=settings.SCRAPER_CACHE_TTL_SECONDS,
)

def get(url: str) -> Optional[Any]:
    """ Consulta cache configurado para obter conteúdo previamente armazenado """
    return _CACHE_ADAPTER.get(url)

def set(url: str, value: Any, ttl_seconds: int) -> None:
    """ Armazena valores da URL mantendo compatibilidade da API pública """
    _CACHE_ADAPTER.set(url, value, ttl_seconds)

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
