""" Utilitários para execução segura de coroutines em contextos síncronos.

Estratégia:
    - Sem loop na thread atual (Celery/script): usa ``asyncio.run()``
    - Loop rodando na thread atual (event loop do FastAPI/uvicorn): PROIBIDO —
      chamar ``.result()`` aqui causaria deadlock. Lança ``RuntimeError`` clara.

Uso correto no FastAPI:
    Sempre delegue para uma thread antes de chamar esta função:
        await asyncio.to_thread(funcao_sincrona_que_usa_run_sync_coro)
"""

from __future__ import annotations

import asyncio
from typing import Any


def run_sync_coro(coro: Any, *, timeout: int = 30) -> Any:
    """Executa uma coroutine de forma segura em contextos síncronos (sem event loop).

    Deve ser chamada APENAS de threads sem event loop ativo (workers Celery,
    scripts, ou threads delegadas via ``asyncio.to_thread``). Chamar do event
    loop do FastAPI/uvicorn causa deadlock imediato.

    Args:
        coro: Coroutine a ser executada.
        timeout: Tempo máximo de espera em segundos (padrão: 30).

    Returns:
        Resultado da coroutine.

    Raises:
        RuntimeError: Se chamada de dentro do event loop ativo (prevenção de deadlock).
        Exception: Qualquer exceção levantada pela coroutine.
    """
    try:
        asyncio.get_running_loop()
        # Se chegou aqui, estamos na thread do event loop — bloquear causaria deadlock.
        raise RuntimeError(
            "run_sync_coro() chamado de dentro do event loop ativo. "
            "Use 'await coro' diretamente, ou delegue para thread com "
            "'await asyncio.to_thread(fn_sincrona)' antes de chamar esta função."
        )
    except RuntimeError as exc:
        if "run_sync_coro()" in str(exc):
            raise
        # asyncio.get_running_loop() lançou RuntimeError — nenhum loop na thread atual.
        # Seguro criar um novo loop com asyncio.run().
        return asyncio.run(coro)
