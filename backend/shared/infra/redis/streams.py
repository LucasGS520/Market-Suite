""" Primitivas de Redis Streams para uso compartilhado entre serviços.

Funções stateless que encapsulam comandos XADD/XLEN/XRANGE.
Erros de conexão são capturados e logados — nunca propagados.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def xadd_event(
    key: str,
    fields: dict[str, Any],
    maxlen: int = 10_000,
) -> str | None:
    """ Adiciona um evento ao stream Redis.

    Usa MAXLEN com aproximação (~) para limitar o tamanho do stream sem
    overhead de trimming exato. Retorna o ID do evento inserido, ou
    ``None`` em caso de falha de conexão.
    """
    from shared.utils.redis_client import get_redis_client

    client = get_redis_client()
    if client is None:
        logger.error("xadd_event_skipped_no_client", extra={"key": key})
        return None
    try:
        event_id = client.xadd(key, fields, maxlen=maxlen, approximate=True)
        return event_id
    except Exception:
        logger.exception("xadd_event_failed", extra={"key": key})
        return None


def xlen_stream(key: str) -> int:
    """ Retorna o número de entradas no stream. Retorna -1 em caso de falha. """
    from shared.utils.redis_client import get_redis_client

    client = get_redis_client()
    if client is None:
        return -1
    try:
        return client.xlen(key)
    except Exception:
        logger.exception("xlen_stream_failed", extra={"key": key})
        return -1


def xrange_stream(key: str, count: int = 100) -> list[tuple]:
    """ Lê as primeiras ``count`` entradas do stream (da mais antiga para a mais nova).

    Retorna lista de tuplas ``(id, fields_dict)`` ou lista vazia em caso de falha.
    """
    from shared.utils.redis_client import get_redis_client

    client = get_redis_client()
    if client is None:
        return []
    try:
        return client.xrange(key, count=count)
    except Exception:
        logger.exception("xrange_stream_failed", extra={"key": key})
        return []


__all__ = ["xadd_event", "xlen_stream", "xrange_stream"]
