""" Fornece cache simples em memória para respostas HTML do scraper

O utilitário expõe operações básicas de consulta e armazenamento com TTL,
registrando métricas para acompanhar hits e misses. A implementação é
thread-safe para suportar múltiplas requisições concorrentes no serviço.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

from shared.metrics.metrics_scraper import SCRAPER_CACHE_LOOKUPS_TOTAL, SCRAPER_CACHE_SIZE


#Futuro: Adptar para Redis quando necessário
@dataclass
class _CacheEntry:
    """ Representa um item armazenado com valor e instante de expiração """
    value: str
    expires_at: float

class _InMemoryCache:
    """ Implementa dicionário protegido por lock para armazenar HTML por URL """
    
    def __init__(self) -> None:
        """ Inicializa estrutura interna e lock para sincronização de acesso """
        self._data: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, url: str) -> Optional[str]:
        """ Recupera valor se não expirado e registra métricas de hit/miss """
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(url)
            if entry is None:
                SCRAPER_CACHE_LOOKUPS_TOTAL.labels(outcome="miss").inc()
                return None
            if entry.expires_at < now:
                #Removemos ao expirar para evitar crescimento descontrolado
                self._data.pop(url, None)
                SCRAPER_CACHE_SIZE.set(len(self._data))
                SCRAPER_CACHE_LOOKUPS_TOTAL.labels(outcome="miss").inc()
                return None
            SCRAPER_CACHE_LOOKUPS_TOTAL.labels(outcome="hit").inc()
            return entry.value
        
    def set(self, url: str, html: str, ttl_seconds: int) -> None:
        """ Armazena HTML associado à URL respeitando o TTL informado """
        expires_at = time.monotonic() + max(ttl_seconds, 0)
        with self._lock:
            #Substituimos qualquer valor anterior para simplificar atualizações
            self._data[url] = _CacheEntry(value=html, expires_at=expires_at)
            SCRAPER_CACHE_SIZE.set(len(self._data))

    def invalidate(self, url: str) -> None:
        """ Remove entrada específica caso exista no cache local """
        with self._lock:
            self._data.pop(url, None)
            SCRAPER_CACHE_SIZE.set(len(self._data))

    def clear(self) -> None:
        """ Limpa todo o conteúdo aramzenado para cenários de manutenção """
        with self._lock:
            self._data.clear()
            SCRAPER_CACHE_SIZE.set(0)

#Instância única para atender funções utilitárias do módulo
_CACHE = _InMemoryCache()

def get(url: str) -> Optional[str]:
    """ Consulta cache em memória para obter HTML prévio da URL recebida """
    return _CACHE.get(url)

def set(url: str, html: str, ttl_seconds: int) -> None:
    """ Adiciona HTML ao cache local com expiração configurável """
    _CACHE.set(url, html, ttl_seconds)

def invalidate(url: str) -> None:
    """ Descarta manualmente item específico armazenado para URL """
    _CACHE.invalidate(url)

def clear() -> None:
    """ Apaga todas as entradas armazenadas pelo cache em memória """
    _CACHE.clear()


__all__ = [
    "get",
    "set",
    "invalidate",
    "clear",
]
