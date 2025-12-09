""" Utilidades simples de lock distribuído via Redis.

As funções abaixo implementam um lock leve baseado em chaves com TTL
para impedir execuções paralelas da mesma unidade lógica. O objetivo
é evitar contendas durante coletas e outras tasks críticas sem
introduzir dependências extras além do Redis já disponível.
"""
from __future__ import annotations

from typing import Final
from uuid import UUID

import structlog

from shared.metrics import metrics_redis
from shared.utils.redis_client import get_redis_client


logger = structlog.get_logger(__name__)
_LOCK_PREFIX: Final = "lock:product:"
_DEFAULT_TTL_SECONDS: Final = 150


def _lock_key(product_id: UUID | str) -> str:
    """ Monta a chave padrão de lock para o produto informado """
    return f"{_LOCK_PREFIX}{product_id}"


def acquire_product_lock(product_id: UUID | str, *, ttl_seconds: int | None = None) -> bool:
    """ Tenta adquirir um lock exclusivo para o produto.

    A função utiliza ``SET NX`` com TTL para evitar que execuções
    paralelas manipulem o mesmo produto. Quando o Redis não estiver
    disponível, consideramos a aquisição como malsucedida para evitar
    comportamentos não determinísticos.
    """
    client = get_redis_client()
    if client is None:
        logger.warning("product_lock_unavailable", product_id=str(product_id))
        return False

    effective_ttl = ttl_seconds or _DEFAULT_TTL_SECONDS
    try:
        acquired = client.set(_lock_key(product_id), "1", ex=effective_ttl, nx=True)
        if acquired:
            metrics_redis.REDIS_LOCK_ACQUIRED_TOTAL.labels(resource="product").inc()
            return True
        metrics_redis.REDIS_LOCK_SKIPPED_TOTAL.labels(resource="product").inc()
        return False
    except Exception:
        logger.exception("product_lock_failed", product_id=str(product_id))
        return False


def release_product_lock(product_id: UUID | str) -> None:
    """ Remove o lock do produto liberando novas execuções """
    client = get_redis_client()
    if client is None:
        return

    try:
        client.delete(_lock_key(product_id))
    except Exception:
        logger.warning("product_lock_release_failed", product_id=str(product_id))