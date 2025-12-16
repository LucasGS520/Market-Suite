""" Testes do lock distribuído garantindo retorno correto de owner e liberação segura. """

from uuid import uuid4

from backend.shared.utils import redis_locks


def test_acquire_lock_success(patch_redis_client):
    produto_id = uuid4()

    adquirido, owner = redis_locks.acquire_product_lock(produto_id, ttl_seconds=5)

    assert adquirido is True
    assert owner is not None
    assert redis_locks._lock_key(produto_id) in patch_redis_client.data
    assert patch_redis_client.data[redis_locks._lock_key(produto_id)] == owner


def test_acquire_lock_returns_existing_owner_bytes(patch_redis_client):
    produto_id = uuid4()
    chave_lock = redis_locks._lock_key(produto_id)
    patch_redis_client.data[chave_lock] = b"owner-anterior"

    adquirido, owner = redis_locks.acquire_product_lock(produto_id, ttl_seconds=5)

    assert adquirido is False
    assert owner == "owner-anterior"


def test_acquire_lock_returns_existing_owner_str(patch_redis_client):
    produto_id = uuid4()
    chave_lock = redis_locks._lock_key(produto_id)
    patch_redis_client.data[chave_lock] = "owner-texto"

    adquirido, owner = redis_locks.acquire_product_lock(produto_id, ttl_seconds=5)

    assert adquirido is False
    assert owner == "owner-texto"


def test_release_product_lock_validates_owner(patch_redis_client):
    produto_id = uuid4()
    adquirido, owner = redis_locks.acquire_product_lock(produto_id, ttl_seconds=5)

    assert adquirido is True
    assert redis_locks.release_product_lock(produto_id, owner) is True
    assert redis_locks._lock_key(produto_id) not in patch_redis_client.data


def test_release_product_lock_rejects_mismatch(patch_redis_client):
    produto_id = uuid4()
    chave_lock = redis_locks._lock_key(produto_id)
    patch_redis_client.data[chave_lock] = "owner-atual"

    assert redis_locks.release_product_lock(produto_id, "owner-divergente") is False
    assert chave_lock in patch_redis_client.data
    