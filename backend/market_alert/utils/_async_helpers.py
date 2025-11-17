""" Utilitários para executar corrotinas dos serviços de forma síncrona """

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar


T = TypeVar("T")

def _run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """ Executa uma corrotina sem interferir no loop de evento global """
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        #Caminho normal em tarefas Celery
        #Cria um loop próprio e garante que ele seja encerrado ao final sem impactar loops compartilhados
        return asyncio.run(coro)
    
    result: dict[str, T | BaseException] = {}

    def _worker() -> None:
        """ Cria um loop dedicado em ``threado`` isolada para evitar conflitos """
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:
            result["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()

    if "error" in result:
        raise result["error"]
    
    if "value" not in result:
        raise RuntimeError("Execução assíncrona não retornou resultado")

    return result["value"]

__all__ = [
    "_run_sync",
]
