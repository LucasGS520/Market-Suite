""" Testes para o módulo de Circuit Breaker do scraper """

from __future__ import annotations

import importlib

import pytest

import market_scraper.utils.circuit_breaker as cb_mod
from market_scraper.utils.circuit_breaker import DomainCircuitBreaker
from market_scraper.utils_controllers.configuration.circuit_breaker_config import CircuitBreakerPolicy

from shared.enums import BlockResult

#Recarregar o módulo para evitar alterações feitas por outros testes
CircuitBreaker = importlib.reload(cb_mod).CircuitBreaker

class FakeRedis:
    def __init__(self) -> None:
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
        (7, 3600),
    ]
    return CircuitBreaker(redis=fake_redis, levels=levels)

def test_allow_request_before_and_after_threshold(cb):
    """ Confirma fechamento do circuito após atingir o primeiro nível """
    key = "circuit:test"
    for _ in range(2):
        assert cb.allow_request(key) is True

    for _ in range(3):
        cb.record_failure(key)

    assert cb.allow_request(key) is False


def test_suspension_ttl_at_level(cb, fake_redis):
    """ Valida que o TTL configurado respeita cada nível de severidade """
    key = "circuit:ttl"
    _, suspend_key = cb._get_keys(key)

    for _ in range(3):
        cb.record_failure(key)
    assert fake_redis.ttl(suspend_key) == 900

    cb.record_success(key)

    for _ in range(5):
        cb.record_failure(key)
    assert fake_redis.ttl(suspend_key) == 1800

    cb.record_success(key)

    for _ in range(7):
        cb.record_failure(key)
    assert fake_redis.ttl(suspend_key) == 1800

def test_record_success_resets_state(cb, fake_redis):
    """ Garante que record_success() limpa contador e chave de suspensão """
    key = "circuit:reset"
    failures_key, suspend_key = cb._get_keys(key)

    for _ in range(3):
        cb.record_failure(key)

    cb.record_success(key)

    assert not fake_redis.exists(failures_key)
    assert not fake_redis.exists(suspend_key)

def test_domain_circuit_breaker_compose_keys(fake_redis):
    """ Assegura que ``DomainCircuitBreaker`` prefixa chaves com o domínio """
    policy = CircuitBreakerPolicy(failure_threshold=3, recovery_time=120)
    base = CircuitBreaker(redis=fake_redis, levels=[(3, 120)])
    domain_cb = DomainCircuitBreaker("example.com", policy, redis=fake_redis)

    domain_cb._breaker = base
    
    domain_cb.record_failure("user")
    assert fake_redis.exists("example.com:user:failures")

    domain_cb.record_success("user")
    assert not fake_redis.exists("example.com:user:failures")

def test_blockresult_enum_values():
    assert BlockResult.HTTP_403.value == "http_403"
    assert BlockResult.CAPTCHA.value == "captcha"
