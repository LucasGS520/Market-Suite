""" Coordena chamadas concorrentes para o mesmo recurso evitando duplicação 

O utilitário aplica o padrão singleflight para que apenas uma corrotina
execute o download enquanto as demais aguardam o resultado compartilhado.
Esse desenho reduz carga sob explosões de requisições e, em cenários de alta
contenção, garante que as requisições concorrentes aproveitem o mesmo
resultado até um limite de tempo configurado.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import structlog

from shared.metrics.metrics_scraper import (
    SCRAPER_SINGLEFLIGHT_CALLS_TOTAL,
    SCRAPER_SINGLEFLIGHT_WAIT_SECONDS,
)
from shared.utils.logging_utils import sanitize_log_data

from market_scraper.core.config_scraper import settings


__all__ = [
    "AsyncSingleFlight",
    "coalesce",
    "reset",
]

T = TypeVar("T")
logger = structlog.get_logger("singleflight")

class _SingleFlightEntry:
    """ Controla o estado compartilhado de uma chamada singleflight """
    
    def __init__(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                #Em cenários de testes síncronos, apenas ``get_event_loop`` pode devolver loop configurado
                loop = asyncio.get_event_loop()
            except RuntimeError as fallback_error:
                raise RuntimeError(
                    "AsyncSingleFlight requer um loop de eventos ativo; execute chamadas dentro de corrotinas."
                ) from fallback_error
        self.future = loop.create_future()
        self.created_at: float = time.monotonic()

    def is_stale(self, *, now: float, ttl: float) -> bool:
        """ Indica se a entrada excedeu o TTL configurado e deve ser reciclada """
        return (now - self.created_at) > ttl
    
class AsyncSingleFlight:
    """ Orquestra execução única por chave para corrotinas assíncronas 
    
    Deve ser usada somente dentro de um contexto assíncrono já associado a um
    loop de eventos ativos para manter a coordenação das futures compartilhadas.
    """
    def __init__(self, *, lock_ttl: float) -> None:
        self._entries: dict[str, _SingleFlightEntry] = {}
        self._entries_lock = asyncio.Lock()
        self._lock_ttl = lock_ttl

    async def coalesce(self, key: str, producer: Callable[[], Awaitable[T]]) -> T:
        """ Agrupa chamadas concorrentes para ``key`` e compartilha o resultado """
        entry, is_leader = await self._acquire_entry(key)
        if is_leader:
            try:
                result = await producer()
            except Exception as exc:
                if not entry.future.done():
                    entry.future.set_exception(exc)
                SCRAPER_SINGLEFLIGHT_CALLS_TOTAL.labels(
                    role="leader", outcome="error"
                ).inc()
                logger.warning(
                    "singleflight_leader_error",
                    key=sanitize_log_data(key),
                    error=sanitize_log_data(str(exc)),
                )
                raise
            else:
                if not entry.future.done():
                    entry.future.set_result(result)
                SCRAPER_SINGLEFLIGHT_CALLS_TOTAL.labels(
                    role="leader", outcome="success"
                ).inc()
                return result
            finally:
                await self._release_entry(key, entry)

        wait_started = time.monotonic()
        try:
            result = await entry.future
        except Exception:
            SCRAPER_SINGLEFLIGHT_CALLS_TOTAL.labels(role="follower", outcome="error").inc()
            raise
        else:
            SCRAPER_SINGLEFLIGHT_CALLS_TOTAL.labels(
                role="follower", outcome="success"
            ).inc()
            return result
        finally:
            wait_duration = max(time.monotonic() - wait_started, 0.0)
            SCRAPER_SINGLEFLIGHT_WAIT_SECONDS.labels(role="follower").observe(wait_duration)
            await self._release_entry(key, entry)

    async def reset(self) -> None:
        """ Limpa entradas pendentes; usando apenas em testes para isolamento """
        async with self._entries_lock:
            for entry in self._entries.values():
                if not entry.future.done():
                    entry.future.cancel()
            self._entries.clear()

    async def _acquire_entry(self, key: str) -> tuple[_SingleFlightEntry, bool]:
        """ Obtém ou cria entrada protegida para ``key`` respeitando TTL """
        async with self._entries_lock:
            now = time.monotonic()
            entry = self._entries.get(key)

            if entry is not None:
                if entry.future.done():
                    self._entries.pop(key, None)
                    entry = None
                elif entry.is_stale(now=now, ttl=self._lock_ttl):
                    if not entry.future.done():
                        entry.future.set_exception(asyncio.TimeoutError("singleflight_stale"))
                    logger.warning(
                        "singleflight_entry_expired",
                        key=sanitize_log_data(key),
                        ttl=self._lock_ttl,
                    )
                    self._entries.pop(key, None)
                    entry = None

            if entry is None:
                entry = _SingleFlightEntry()
                self._entries[key] = entry
                return entry, True
            
            return entry, False
        
    async def _release_entry(self, key: str, entry: _SingleFlightEntry) -> None:
        """ Recicla a entrada associada após concluir a operação compartilhada """
        if not entry.future.done():
            return
        
        async with self._entries_lock:
            current = self._entries.get(key)
            if current is entry:
                self._entries.pop(key, None)

_singleflight = AsyncSingleFlight(lock_ttl=settings.SCRAPER_SINGLEFLIGHT_LOCK_TTL)

async def coalesce(key: str, producer: Callable[[], Awaitable[T]]) -> T:
    """ Executa ``producer`` apenas uma vez por chave e compartilha o retorno """
    return await _singleflight.coalesce(key, producer)

async def reset() -> None:
    """ Limpa o estado interno global; reservado para testes """
    await _singleflight.reset()
    