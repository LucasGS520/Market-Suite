""" Utilidades simples de lock distribuído via Redis.

As funções abaixo implementam um lock leve baseado em chaves com TTL
para impedir execuções paralelas da mesma unidade lógica. O objetivo
é evitar contendas durante coletas e outras tasks críticas sem
introduzir dependências extras além do Redis já disponível. O TTL
adota ``PRODUCT_LOCK_TTL_SECONDS`` quando definido no ambiente para
permitir tunning operacional sem alterar código.
"""
from __future__ import annotations

import os
from typing import Final
from uuid import UUID, uuid4

import structlog

from shared.metrics import metrics_redis
from shared.utils.redis_client import get_redis_client


logger = structlog.get_logger(__name__)
_LOCK_PREFIX: Final = "lock:product:"
_DEFAULT_TTL_SECONDS: Final = int(os.getenv("PRODUCT_LOCK_TTL_SECONDS", "30"))

_RELEASE_SCRIPT: Final = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def _lock_key(product_id: UUID | str) -> str:
    """ Monta a chave padrão de lock para o produto informado """
    return f"{_LOCK_PREFIX}{product_id}"


def acquire_product_lock(product_id: UUID | str, *, ttl_seconds: int | None = None) -> str | None:
    """ Tenta adquirir um lock exclusivo para o produto e retorna o token.

    O valor armazenado na chave é um token único que identifica o dono do
    lock. Dessa forma, a liberação só ocorre quando o mesmo token é
    informado, evitando que processos atrasados removam locks recém
    adquiridos por outros workers. Quando o Redis não estiver disponível,
    consideramos a aquisição como malsucedida para manter a previsibilidade.
    """
    client = get_redis_client()
    if client is None:
        logger.warning("product_lock_unavailable", product_id=str(product_id))
        return None

    effective_ttl = ttl_seconds or _DEFAULT_TTL_SECONDS
    token = str(uuid4())
    try:
        acquired = client.set(_lock_key(product_id), token, ex=effective_ttl, nx=True)
        if acquired:
            metrics_redis.REDIS_LOCK_ACQUIRED_TOTAL.labels(resource="product").inc()
            return token
        
        metrics_redis.REDIS_LOCK_SKIPPED_TOTAL.labels(resource="product").inc()
        return None
    
    except Exception:
        logger.exception("product_lock_failed", product_id=str(product_id))
        return None
    
def release_product_lock(product_id: UUID | str, token: str | None) -> bool:
    """ Remove o lock do produto validando o token informado

    A liberação é feita via script Lua que confirma se o token gravado na
    chave é o mesmo recebido. Caso o lock já tenha expirado ou sido
    adquirido por outro worker, a função apenas registra a inconsistência
    sem apagar a chave, preservando a segurança do lock distribuído.
    """
    if token is None:
        logger.warning("product_lock_release_skipped", product_id=str(product_id), reason="missing_token")
        return False

    client = get_redis_client()
    if client is None:
        return False

    try:
        released = client.eval(_RELEASE_SCRIPT, 1, _lock_key(product_id), token)
        if released:
            return True

        metrics_redis.REDIS_LOCK_RELEASE_FAILED_TOTAL.labels(resource="product").inc()
        logger.warning("product_lock_release_failed", product_id=str(product_id), reason="mismatch_or_expired")
        return False
    
    except Exception:
        metrics_redis.REDIS_LOCK_RELEASE_FAILED_TOTAL.labels(resource="product").inc()
        logger.warning("product_lock_release_failed", product_id=str(product_id), reason="exception")
        return False
    