""" Utilidades simples de lock distribuído via Redis.

As funções abaixo implementam um lock leve baseado em chaves com TTL
para impedir execuções paralelas da mesma unidade lógica. O valor do
lock registra o identificador do dono, permitindo auditoria em logs e
liberação segura apenas pelo proprietário. O TTL adota
``PRODUCT_LOCK_TTL_SECONDS`` quando definido no ambiente para permitir
ajuste operacional sem alterar código.
"""

from __future__ import annotations

import os
import socket
from typing import Final
from uuid import UUID, uuid4

import structlog

from shared.metrics import metrics_redis
from shared.utils.redis_client import get_redis_client


logger = structlog.get_logger(__name__)
_ENV_NAMESPACE: Final = (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "").strip()
_LOCK_PREFIX: Final = f"lock:{_ENV_NAMESPACE}:" if _ENV_NAMESPACE else "lock:"
_DEFAULT_TTL_SECONDS: Final = int(os.getenv("PRODUCT_LOCK_TTL_SECONDS", "20"))
_MIN_SAFE_TTL_SECONDS: Final = int(os.getenv("PRODUCT_LOCK_TTL_MIN_SAFE_SECONDS", "15"))

_RELEASE_SCRIPT: Final = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

_REFRESH_SCRIPT: Final = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""


def _lock_key_product(product_id: UUID | str) -> str:
    """ Monta a chave padrão de lock para o produto informado """
    #Incluímos namespace de ambiente para evitar colisão entre stacks compartilhando Redis
    return f"{_LOCK_PREFIX}product:{product_id}"

def _lock_key_continuous_collector() -> str:
    """ Monta chave padrão de lock para o coletor contínuo """
    return f"{_LOCK_PREFIX}continuous_collector"

def _lock_key_notification(dedup_key: str) -> str:
    """ Monta chave padrão de lock para notificação com deduplicação """
    return f"{_LOCK_PREFIX}notification:{dedup_key}"

def _resolve_owner_id() -> str:
    """ Gera identificador curto do dono do lock para rastreamento """
    hostname = socket.gethostname()
    pid = os.getpid()
    return f"{hostname}:{pid}:{uuid4().hex[:8]}"

# ----- Lock de produto -----
def acquire_product_lock(product_id: UUID | str, *, ttl_seconds: int | None = None) -> tuple[bool, str | None]:
    """ Tenta adquirir um lock exclusivo para o produto e retorna estado e dono.

    O valor armazenado na chave é um identificador curto do proprietário. A
    liberação só ocorre quando o mesmo identificador é informado, evitando que
    processos atrasados removam locks recém-adquiridos por outros workers.
    Quando o Redis não estiver disponível, consideramos a aquisição como
    malsucedida para manter a previsibilidade.
    """
    client = get_redis_client()
    if client is None:
        logger.warning("product_lock_unavailable", product_id=str(product_id))
        return False, None

    effective_ttl = ttl_seconds or _DEFAULT_TTL_SECONDS
    owner_id = _resolve_owner_id()
    try:
        acquired = client.set(
            _lock_key_product(product_id),
            owner_id,
            px=int(effective_ttl * 1000),
            nx=True,
        )
        if acquired:
            metrics_redis.REDIS_LOCK_ACQUIRED_TOTAL.labels(resource="product").inc()
            return True, owner_id
        
        existing_owner = client.get(_lock_key_product(product_id))
        metrics_redis.REDIS_LOCK_SKIPPED_TOTAL.labels(resource="product").inc()
        if existing_owner is None:
            return False, None

        if isinstance(existing_owner, bytes):
            return False, existing_owner.decode("utf-8")

        return False, str(existing_owner)
    
    except Exception:
        logger.exception("product_lock_failed", product_id=str(product_id))
        return False, None
    
def release_product_lock(product_id: UUID | str, owner_id: str | None) -> bool:
    """ Remove o lock do produto validando o dono informado.

    A liberação é feita via script Lua que confirma se o token gravado na
    chave é o mesmo recebido. Caso o lock já tenha expirado ou sido
    adquirido por outro worker, a função apenas registra a inconsistência
    sem apagar a chave, preservando a segurança do lock distribuído.
    """
    if owner_id is None:
        logger.warning("product_lock_release_skipped", product_id=str(product_id), reason="missing_owner")
        return False

    client = get_redis_client()
    if client is None:
        return False

    try:
        released = client.eval(_RELEASE_SCRIPT, 1, _lock_key_product(product_id), owner_id)
        if released:
            return True

        metrics_redis.REDIS_LOCK_RELEASE_FAILED_TOTAL.labels(resource="product").inc()
        logger.warning("product_lock_release_failed", product_id=str(product_id), reason="mismatch_or_expired")
        return False
    
    except Exception:
        metrics_redis.REDIS_LOCK_RELEASE_FAILED_TOTAL.labels(resource="product").inc()
        logger.warning("product_lock_release_failed", product_id=str(product_id), reason="exception")
        return False
    
def get_product_lock_defaults() -> tuple[int, int]:
    """ Retorna TTL padrão configurado e margem mínima recomendada """
    return _DEFAULT_TTL_SECONDS, _MIN_SAFE_TTL_SECONDS

# ----- Lock do coletor contínuo -----
def acquire_continuous_collector_lock(*, ttl_seconds: int) -> tuple[bool, str | None]:
    """ Tenta adquirir lock exclusivo para o loop contínuo e retorna estado e dono """
    client = get_redis_client()
    if client is None:
        logger.warning("continuous_collector_lock_unavailable", reason="redis_unavailable")
        return False, None
    
    owner_id = _resolve_owner_id()
    try:
        acquired = client.set(
            _lock_key_continuous_collector(),
            owner_id,
            px=int(ttl_seconds * 1000),
            nx=True,
        )
        if acquired:
            metrics_redis.REDIS_LOCK_ACQUIRED_TOTAL.labels(resource="continuous_collector").inc()
            return True, owner_id
        
        existing_owner = client.get(_lock_key_continuous_collector())
        metrics_redis.REDIS_LOCK_SKIPPED_TOTAL.labels(resource="continuous_collector").inc()
        if existing_owner is None:
            return False, None
        
        if isinstance(existing_owner, bytes):
            return False, existing_owner.decode("utf-8")
        
        return False, str(existing_owner)
    except Exception:
        logger.exception("continuous_collector_lock_failed")
        return False, None
    
def refresh_continuous_collector_lock(*, owner_id: str | None, ttl_seconds: int) -> bool:
    """ Renova o TTL do lock do coletor contínuo preservando o dono """
    if owner_id is None:
        logger.warning(
            "continuous_collector_lock_refresh_skipped",
            reason="missing_owner",
        )
        return False
    
    client = get_redis_client()
    if client is None:
        logger.warning(
            "continuous_collector_lock_refresh_skipped",
            reason="redis_unavailable",
        )
        return False
    
    try:
        refreshed = client.eval(
            _REFRESH_SCRIPT,
            1,
            _lock_key_continuous_collector(),
            owner_id,
            int(ttl_seconds * 1000),
        )
        return bool(refreshed)
    except Exception:
        logger.exception("continuous_collector_lock_refresh_failed")
        return False
    
def release_continuous_collector_lock(*, owner_id: str | None) -> bool:
    """ Libera o lock do coletor contínuo validando o dono informado """
    if owner_id is None:
        logger.warning(
            "continuous_collector_lock_release_skipped",
            reason="missing_owner",
        )
        return False
    
    client = get_redis_client()
    if client is None:
        return False
    
    try:
        released = client.eval(
            _RELEASE_SCRIPT,
            1,
            _lock_key_continuous_collector(),
            owner_id,
        )
        if released:
            return True
        
        metrics_redis.REDIS_LOCK_RELEASE_FAILED_TOTAL.labels(
            resource="continuous_collector"
        ).inc()
        logger.warning(
            "continuous_collector_lock_release_failed",
            reason="mismatch_or_expired",
        )
        return False
    except Exception:
        metrics_redis.REDIS_LOCK_RELEASE_FAILED_TOTAL.labels(
            resource="continuous_collector"
        ).inc()
        logger.warning(
            "continuous_collector_lock_release_failed",
            reason="exception",
        )
        return False

# ----- Lock de notificação com deduplicação -----
def acquire_notification_lock(dedup_key: str, *, ttl_seconds: int | None = None) -> tuple[bool, str | None]:
    """ Tenta adquirir um lock exclusivo para a deduplicação informada """
    client = get_redis_client()
    if client is None:
        logger.warning("notification_lock_unavailable", dedup_key=dedup_key)
        return False, None
    
    effective_ttl = ttl_seconds or _DEFAULT_TTL_SECONDS
    owner_id = _resolve_owner_id()
    try:
        acquired = client.set(
            _lock_key_notification(dedup_key),
            owner_id,
            px=int(effective_ttl * 1000),
            nx=True,
        )
        if acquired:
            metrics_redis.REDIS_LOCK_ACQUIRED_TOTAL.labels(resource="notification").inc()
            return True, owner_id
        
        existing_owner = client.get(_lock_key_notification(dedup_key))
        metrics_redis.REDIS_LOCK_SKIPPED_TOTAL.labels(resource="notification").inc()
        if existing_owner is None:
            return False, None
        
        if isinstance(existing_owner, bytes):
            return False, existing_owner.decode("utf-8")
        
        return False, str(existing_owner)
    
    except Exception:
        logger.exception("notification_lock_failed", dedup_key=dedup_key)
        return False, None
    
def release_notification_lock(dedup_key: str, owner_id: str | None) -> bool:
    """ Remove o lock de notificação validando o dono informado """
    if owner_id is None:
        logger.warning("notification_lock_release_skipped", dedup_key=dedup_key, reason="missing_owner")
        return False
    
    client = get_redis_client()
    if client is None:
        return False
    
    try:
        released = client.eval(_RELEASE_SCRIPT, 1, _lock_key_notification(dedup_key), owner_id)
        if released:
            return True
        
        metrics_redis.REDIS_LOCK_RELEASE_FAILED_TOTAL.labels(resource="notification").inc()
        logger.warning("notification_lock_release_failed", dedup_key=dedup_key, reason="mismatch_or_expired")
        return False
    
    except Exception:
        metrics_redis.REDIS_LOCK_RELEASE_FAILED_TOTAL.labels(resource="notification").inc()
        logger.warning("notification_lock_release_failed", dedup_key=dedup_key, reason="exception")
        return False
