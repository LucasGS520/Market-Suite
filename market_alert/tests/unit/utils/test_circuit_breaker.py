import importlib
import pytest
import utils.circuit_breaker as cb_mod

#Recarregar o módulo para evitar alterações feitas por outros testes
CircuitBreaker = importlib.reload(cb_mod).CircuitBreaker

class FakeRedis:
    def __init__(self):
        self.store = {}
        self.ttl_store = {}

    def set(self, key, value, ex=None):
        self.store[key] = value
        if ex:
            self.ttl_store[key] = ex

    def ttl(self, key):
        return self.ttl_store.get(key)

    def incr(self, key):
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def expire(self, key, ex):
        self.ttl_store[key] = ex

    def exists(self, key):
        return key in self.store

    def delete(self, key):
        self.store.pop(key, None)
        self.ttl_store.pop(key, None)


@pytest.fixture()
def fake_redis():
    return FakeRedis()

@pytest.fixture()
def cb(fake_redis):
    levels = [
        (3, 900),
        (5, 1800),
        (7, 3600)
    ]
    return CircuitBreaker(redis=fake_redis, levels=levels)

def test_allow_request_before_and_after_threshold(cb, fake_redis):
    """ Antes de atingir o limite de falhas, allow_request() retorna True
    Após ultrapassar o nivel 1, retorna False """
    key = "circuit:test"

    for _ in range(2):
        assert cb.allow_request(key) is True

    cb.record_failure(key)
    cb.record_failure(key)
    cb.record_failure(key)

    #ainda abaixo do threshold
    assert cb.allow_request(key) is False


def test_suspension_ttl_at_level(cb, fake_redis):
    """ Testa ao atingir diferentes niveis de falhas
    TTL da suspensão é apropriado """
    key = "circuit:ttl"
    _, suspend_key = cb._gets_keys(key)

    #Level 1 -> 3 falhas
    for _ in range(3):
        cb.record_failure(key)
    assert fake_redis.ttl(suspend_key) == 900

    #Reseta para testar level 2
    cb.record_success(key)

    #Level 2 -> 5 falhas
    for _ in range(5):
        cb.record_failure(key)
    assert fake_redis.ttl(suspend_key) == 1800

    #Reseta para testar level 3
    cb.record_success(key)

    #Level 3 -> 7 falhas
    for _ in range(7):
        cb.record_failure(key)
    assert fake_redis.ttl(suspend_key) == 1800

def test_record_success_resets_state(cb, fake_redis):
    """ Confirma que record_success() limpa contador e chave de suspensão """
    key = "circuit:reset"
    failures_key, suspend_key = cb._gets_keys(key)

    #Causa falhas para ativar suspensão
    for _ in range(3):
        cb.record_failure(key)

    #Chama sucesso -> deve limpar tudo
    cb.record_success(key)

    assert not fake_redis.exists(failures_key)
    assert not fake_redis.exists(suspend_key)
