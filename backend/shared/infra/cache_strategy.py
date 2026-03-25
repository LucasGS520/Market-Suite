"""Padrão Cache-Aside para leitura de dados de negócio

Estratégia:
  1. Tenta ler do Redis (hit → retorna imediatamente)
  2. Em caso de miss, chama fetch_fn (query PostgreSQL)
  3. Armazena resultado no Redis com TTL
  4. Retorna resultado

PostgreSQL é sempre o source de verdade.
Redis é "nice-to-have": pode estar stale, pode estar indisponível.
Em caso de falha do Redis, o sistema degrada graciosamente lendo direto do banco.

Uso:
    def _fetch():
        return db.query(...).<serializable dict>

    resultado = get_with_cache(
        key=CacheKey.product_price(product_id),
        ttl=settings.REDIS_TTL_CACHE_DATA_SECONDS,
        fetch_fn=_fetch,
    )
"""

from __future__ import annotations

import json
from typing import Any, Callable, TypeVar

import structlog

from shared.utils.redis_client import get_redis_operational


logger = structlog.get_logger(__name__)

T = TypeVar("T")

def get_with_cache(
    key: str,
    ttl: int,
    fetch_fn: Callable[[], T | None],
) -> T | None:
    """Cache-aside genérico.

    Args:
        key: Chave Redis (ex: ``CacheKey.product_price(id)``).
        ttl: TTL em segundos para popular o cache no miss.
        fetch_fn: Callable sem args que retorna dado JSON-serializável ou None.

    Returns:
        Resultado do cache (hit) ou de fetch_fn (miss).
        fetch_fn deve retornar dict/list/primitive — NÃO objetos ORM.

    Nota:
        Falhas do Redis são silenciadas; o sistema sempre chega ao fetch_fn.
    """
    # --- Tentativa de cache hit ---
    try:
        client = get_redis_operational()
        cached = client.get(key)
        if cached is not None:
            logger.debug("cache_hit", key=key)
            return json.loads(cached)
    except Exception as exc:
        logger.warning("cache_get_failed", key=key, error=str(exc))

    # --- Cache miss: busca no PostgreSQL ---
    result = fetch_fn()

    # --- Popula cache apenas se há resultado válido ---
    if result is not None:
        try:
            client = get_redis_operational()
            client.setex(key, ttl, json.dumps(result, default=str))
            logger.debug("cache_populated", key=key, ttl=ttl)
        except Exception as exc:
            logger.warning("cache_set_failed", key=key, error=str(exc))

    return result

def invalidate(key: str) -> None:
    """Remove uma chave de cache do Redis.

    Fallback silencioso: se o Redis estiver indisponível, o dado
    simplesmente não é invalidado — expirará via TTL.
    """
    try:
        client = get_redis_operational()
        deleted = client.delete(key)
        logger.debug("cache_invalidated", key=key, deleted=bool(deleted))
    except Exception as exc:
        logger.warning("cache_invalidate_failed", key=key, error=str(exc))

def invalidate_pattern(pattern: str) -> None:
    """Invalida todas as chaves Redis que casam com o padrão (via SCAN).

    Usa SCAN incremental para evitar bloqueio em bases grandes.
    Exemplo de padrão: ``cache:product:123:*``
    """
    try:
        client = get_redis_operational()
        cursor = 0
        total_deleted = 0
        while True:
            cursor, keys = client.scan(cursor, match=pattern, count=100)
            if keys:
                client.delete(*keys)
                total_deleted += len(keys)
            if cursor == 0:
                break
        logger.debug("cache_pattern_invalidated", pattern=pattern, deleted=total_deleted)
    except Exception as exc:
        logger.warning("cache_invalidate_pattern_failed", pattern=pattern, error=str(exc))


__all__ = ["get_with_cache", "invalidate", "invalidate_pattern"]
