""" Utilitários para executar corrotinas dos serviços de forma síncrona """

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar


T = TypeVar("T")

def _run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """ Executa corrotina garantindo gerenciamento seguro do loop de evento """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
            asyncio.set_event_loop(None)

    if loop.is_closed():
        asyncio.set_event_loop(None)
        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
            asyncio.set_event_loop(None)

    if loop.is_running():
        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
            asyncio.set_event_loop(None)

    return loop.run_until_complete(coro)


__all__ = [
    "_run_sync",
]
