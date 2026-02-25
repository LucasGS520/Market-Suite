""" Contexto de trace_id para propagação silenciosa entre camadas.

Utiliza ``contextvars.ContextVar`` para armazenar o trace_id do ciclo
de execução atual de forma thread-safe e async-safe, sem precisar passar
o valor como parâmetro em cada chamada de função.

Uso típico em tasks Celery::

    from shared.utils.trace_context import set_trace_id, get_trace_id

    def my_task(self, ..., trace_id=None):
        set_trace_id(trace_id or self.request.id)
        ...

Uso em services para obter o ID atual::

    from shared.utils.trace_context import get_trace_id

    logger.info("evento", trace_id=get_trace_id())
"""

from __future__ import annotations

import contextvars
from uuid import uuid4


_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)


def set_trace_id(trace_id: str) -> None:
    """ Define o trace_id para o contexto de execução atual. """
    _trace_id_var.set(trace_id)

def get_trace_id() -> str | None:
    """ Retorna o trace_id do contexto atual, ou None se não definido. """
    return _trace_id_var.get()

def get_or_create_trace_id() -> str:
    """ Retorna o trace_id atual ou gera e registra um novo UUID se ausente. """
    tid = _trace_id_var.get()
    if tid is None:
        tid = str(uuid4())
        _trace_id_var.set(tid)
    return tid

def clear_trace_id() -> None:
    """ Remove o trace_id do contexto atual (útil em testes). """
    _trace_id_var.set(None)


__all__ = [
    "set_trace_id",
    "get_trace_id",
    "get_or_create_trace_id",
    "clear_trace_id",
]
