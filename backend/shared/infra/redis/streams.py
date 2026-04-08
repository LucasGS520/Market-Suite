""" Primitivas de Redis Streams para uso compartilhado entre serviços.

Funções stateless que encapsulam comandos XADD/XREAD e operações básicas
de consumer groups. Erros de conexão são capturados e logados — nunca
propagados.
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
    from shared.utils.redis_client import get_redis_operational

    client = get_redis_operational()
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
    from shared.utils.redis_client import get_redis_operational

    client = get_redis_operational()
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
    from shared.utils.redis_client import get_redis_operational

    client = get_redis_operational()
    if client is None:
        return []
    try:
        return client.xrange(key, count=count)
    except Exception:
        logger.exception("xrange_stream_failed", extra={"key": key})
        return []


def xread_stream(
    key: str,
    *,
    last_id: str = "0-0",
    count: int = 100,
    block_ms: int | None = None,
) -> list[tuple]:
    """ Lê entradas novas do stream a partir de ``last_id``.

    Retorna apenas a lista de eventos do stream solicitado para manter o
    helper simples para consumidores que lidam com um stream por vez.
    """
    from shared.utils.redis_client import get_redis_operational

    client = get_redis_operational()
    if client is None:
        return []
    try:
        kwargs = {"count": count}
        if block_ms is not None:
            kwargs["block"] = block_ms
        response = client.xread({key: last_id}, **kwargs)
        if not response:
            return []
        return response[0][1]
    except Exception:
        logger.exception("xread_stream_failed", extra={"key": key})
        return []


def ensure_consumer_group(
    key: str,
    *,
    group: str,
    start_id: str = "0-0",
    mkstream: bool = True,
) -> bool:
    """ Garante a existência de um consumer group para o stream.

    Quando o grupo já existir, o helper trata a condição como sucesso.
    """
    from shared.utils.redis_client import get_redis_operational

    client = get_redis_operational()
    if client is None:
        return False
    try:
        client.xgroup_create(name=key, groupname=group, id=start_id, mkstream=mkstream)
        return True
    except Exception as exc:
        if "BUSYGROUP" in str(exc):
            return True
        logger.exception("xgroup_create_failed", extra={"key": key, "group": group})
        return False


def xreadgroup_stream(
    key: str,
    *,
    group: str,
    consumer: str,
    last_id: str = ">",
    count: int = 100,
    block_ms: int | None = None,
) -> list[tuple]:
    """ Lê eventos usando um consumer group Redis."""
    from shared.utils.redis_client import get_redis_operational

    client = get_redis_operational()
    if client is None:
        return []
    try:
        kwargs = {
            "groupname": group,
            "consumername": consumer,
            "streams": {key: last_id},
            "count": count,
        }
        if block_ms is not None:
            kwargs["block"] = block_ms
        response = client.xreadgroup(**kwargs)
        if not response:
            return []
        return response[0][1]
    except Exception:
        logger.exception(
            "xreadgroup_stream_failed",
            extra={"key": key, "group": group, "consumer": consumer},
        )
        return []


def xack_stream(key: str, *, group: str, event_id: str) -> int:
    """ Reconhece um evento já processado por um consumer group."""
    from shared.utils.redis_client import get_redis_operational

    client = get_redis_operational()
    if client is None:
        return 0
    try:
        return int(client.xack(key, group, event_id))
    except Exception:
        logger.exception("xack_stream_failed", extra={"key": key, "group": group})
        return 0


__all__ = [
    "xadd_event",
    "xlen_stream",
    "xrange_stream",
    "xread_stream",
    "ensure_consumer_group",
    "xreadgroup_stream",
    "xack_stream",
]
