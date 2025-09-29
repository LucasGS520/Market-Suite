""" Testes para o módulo de Circuit Breaker do scraper """

from __future__ import annotations

import importlib

import pytest

import market_scraper.utils.circuit_breaker as cb_mod
from market_scraper.utils_controllers.configuration.circuit_breaker_config import CircuitBreakerPolicy

from shared.enums import BlockResult
from shared.metrics import metrics_scraper

cb_mod = importlib.reload(cb_mod)
CircuitBreaker = cb_mod.CircuitBreaker
DomainCircuitBreaker = cb_mod.DomainCircuitBreaker
CircuitBreakerDecision = cb_mod.CircuitBreakerDecision

class FakeRedis:
    """ Implementação mínima de Redis em memória para cenários de testes """

    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.ttl_store: dict[str, int] = {}

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

    def delete(self, *keys):
        removed = 0
        for key in keys:
            if key in self.store:
                removed += 1
                self.store.pop(key, None)
            if key in self.ttl_store:
                self.ttl_store.pop(key, None)
        return removed

@pytest.fixture()
def fake_redis():
    return FakeRedis()

@pytest.fixture(autouse=True)
def reset_circuit_metrics():
    """ Garante que as métricas do circuito iniciem limpas a cada caso de teste """
    for metric in (
        metrics_scraper.SCRAPER_CIRCUIT_ATTEMPTS_TOTAL,
        metrics_scraper.SCRAPER_CIRCUIT_STATE,
        metrics_scraper.SCRAPER_CIRCUIT_TRANSITIONS_TOTAL,
        metrics_scraper.SCRAPER_CIRCUIT_SUSPENSIONS_TOTAL,
    ):
        metric.clear()

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

    assert cb.record_success(key) is True

    assert not fake_redis.exists(failures_key)
    assert not fake_redis.exists(suspend_key)

def test_domain_circuit_breaker_compose_keys(fake_redis):
    """ Assegura que ``DomainCircuitBreaker`` prefixa chaves com o domínio """
    policy = CircuitBreakerPolicy(failure_threshold=3, recovery_time=120)
    domain_cb = DomainCircuitBreaker("example.com", policy, redis=fake_redis)

    decision = domain_cb.record_failure("user")
    assert isinstance(decision, CircuitBreakerDecision)
    assert fake_redis.exists("example.com:user:failures")

    closed = domain_cb.record_success("user")
    assert closed is True
    assert not fake_redis.exists("example.com:user:failures")

def test_record_failure_returns_decision_details(cb):
    """ Confere que o ``CircuitBreaker`` devolve detalhes da decisão """
    key = "decision:test"

    decision = cb.record_failure(key)
    assert isinstance(decision, CircuitBreakerDecision)
    assert decision.failure_count == 1
    assert decision.opened is False

    for _ in range(2):
        decision = cb.record_failure(key)

    assert decision.opened is True
    assert decision.level == 1
    assert decision.suspend_seconds == 900

def test_domain_circuit_breaker_updates_metrics_and_blocks(fake_redis):
    """ Valida métricas e bloqueio após atingir o limiar configurados """
    policy = CircuitBreakerPolicy(failure_threshold=2, recovery_time=60)
    domain_cb = DomainCircuitBreaker("example.com", policy, redis=fake_redis)

    assert (
        metrics_scraper.SCRAPER_CIRCUIT_STATE.labels(host="example.com", state="closed")._value.get() == 1
    )

    assert domain_cb.allow_request() is True

    decision = domain_cb.record_failure()
    assert decision.opened is False

    decision = domain_cb.record_failure()
    assert decision.opened is True

    blocked = domain_cb.allow_request()
    assert blocked is False

    assert (
        metrics_scraper.SCRAPER_CIRCUIT_ATTEMPTS_TOTAL.labels(host="example.com", result="failure")._value.get() == 2
    )

    assert (
        metrics_scraper.SCRAPER_CIRCUIT_ATTEMPTS_TOTAL.labels(host="example.com", result="blocked")._value.get() == 1
    )

    assert (
        metrics_scraper.SCRAPER_CIRCUIT_TRANSITIONS_TOTAL.labels(host="example.com", state="open")._value.get() == 1
    )

    assert (
        metrics_scraper.SCRAPER_CIRCUIT_SUSPENSIONS_TOTAL.labels(host="example.com", level="level_1")._value.get() == 1
    )

    domain_cb.record_success()
    assert (
        metrics_scraper.SCRAPER_CIRCUIT_TRANSITIONS_TOTAL.labels(host="example.com", state="closed")._value.get() == 1
    )

def test_allow_request_fail_open_on_redis_error():
    """ Garante comportamento fail-open em caso de erro ao consultar no Redis """
    class ErrorRedis(FakeRedis):
        def exists(self, key):
            raise RuntimeError("boom")
        
    breaker = CircuitBreaker(redis=ErrorRedis())
    assert breaker.allow_request("teste") is True

def test_record_failure_handles_redis_error():
    """ Confirma que o registro de falha lida com exeções do Redis """
    class ErrorIncrRedis(FakeRedis):
        def incr(self, key):
            raise RuntimeError("falha")
        
    breaker = CircuitBreaker(redis=ErrorIncrRedis())
    decision = breaker.record_failure("erro")
    assert decision.opened is False
    assert decision.failure_count == 0

def test_blockresult_enum_values():
    assert BlockResult.HTTP_403.value == "http_403"
    assert BlockResult.CAPTCHA.value == "captcha"
