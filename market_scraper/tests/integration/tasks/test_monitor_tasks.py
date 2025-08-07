"""Testes das tarefas de monitoramento programado."""

import importlib
from unittest.mock import Mock

import pytest

import app.utils.redis_client as _rc_mod
import app.utils.rate_limiter as _rl_mod
import app.utils.circuit_breaker as _cb_mod
import app.tasks.compare_prices_tasks as _cp_mod

class DummyRedis:
    def get(self, *a, **k):
        return None
    def exists(self, *a, **k):
        return False
    def set(self, *a, **k):
        pass


class DummyRateLimiter:
    def __init__(self, *a, **k):
        pass
    def allow_request(self, *a, **k):
        return True
    def reset(self, *a, **k):
        pass
    def get_count(self, *a, **k):
        return 0


class DummyCircuitBreaker:
    def allow_request(self, *a, **k):
        return True
    def record_success(self, *a, **k):
        pass
    def record_failure(self, *a, **k):
        pass


class DummyCompare:
    @staticmethod
    def delay(*args, **kwargs):
        pass

# ---------- IMPORTAÇÃO MONITOR_TASKS ----------
@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    monkeypatch.setattr(_rc_mod, "get_redis_client", lambda: DummyRedis())
    monkeypatch.setattr(_rl_mod, "RateLimiter", DummyRateLimiter)
    monkeypatch.setattr(_cb_mod, "CircuitBreaker", lambda: DummyCircuitBreaker())
    monkeypatch.setattr(_cp_mod, "compare_prices_task", DummyCompare)

    monitor_tasks = importlib.reload(importlib.import_module("alert_app.tasks.monitor_tasks"))
    monkeypatch.setattr(monitor_tasks, "redis_client", DummyRedis())
    monkeypatch.setattr(monitor_tasks, "circuit_breaker", DummyCircuitBreaker())
    monkeypatch.setattr(monitor_tasks, "scraping_dispatch_limiter", DummyRateLimiter())
    monkeypatch.setattr(monitor_tasks, "competitor_dispatch_limiter", DummyRateLimiter())
    return monitor_tasks

# ---------- BLOCO PARA RECHECK MONITORED ----------
def test_recheck_monitored_circuitbreaker_open(setup_env, monkeypatch):
    """ Circuit breaker não permite -> deve retornar silenciosamente """
    monitor_tasks = setup_env

    monkeypatch.setattr(monitor_tasks.circuit_breaker, "allow_request", lambda *a, **k: False)
    monitor_tasks.recheck_monitored_products()

def test_recheck_monitored_scraping_suspended(setup_env, monkeypatch):
    """ Flag global Redis 'scraping_suspended' ativa -> task encerra silenciosamente """
    monitor_tasks = setup_env

    monkeypatch.setattr(monitor_tasks, "is_scraping_suspended", lambda: True)
    monitor_tasks.recheck_monitored_products()

def test_recheck_monitored_dispatch_limit_exceeded(setup_env):
    """ Scraping_dispatch_limiter -> allow_request=False -> não dispara subtasks """
    monitor_tasks = setup_env

    monitor_tasks.scraping_dispatch_limiter.allow_request = lambda *a, **k: False
    monitor_tasks.recheck_monitored_products()

def test_recheck_monitored_calls_collect(setup_env, monkeypatch):
    """ Quando tudo está permitido, deve buscar produtos e chamar collect_product_task.delay() """
    monitor_tasks = setup_env

    monkeypatch.setattr(monitor_tasks.circuit_breaker, "allow_request", lambda *a, **k: True)
    monitor_tasks.redis_client = DummyRedis()
    monitor_tasks.scraping_dispatch_limiter.allow_request = lambda *a, **k: True

    fake_products = [
        Mock(product_url="u1", user_id="user1", name_identification="n1", target_price=10),
        Mock(product_url="u2", user_id="user2", name_identification="n2", target_price=20)
    ]
    monkeypatch.setattr(monitor_tasks, "get_products_by_type", lambda *a, **k: fake_products)

    called = []
    class FakeTask:
        @staticmethod
        def delay(url, user_id, name_identification, target_price):
            called.append((url, user_id, name_identification, target_price))

    monkeypatch.setattr(monitor_tasks, "collect_product_task", FakeTask)
    monitor_tasks.recheck_monitored_products()

    assert called == [
        ("u1", "user1", "n1", 10),
        ("u2", "user2", "n2", 20)
    ]


# ---------- BLOCO PARA RECHECK COMPETITOR ----------
def test_recheck_competitor_circuitbreaker_open(setup_env, monkeypatch):
    monitor_tasks = setup_env

    monkeypatch.setattr(monitor_tasks.circuit_breaker, "allow_request", lambda *a, **k: False)
    monitor_tasks.recheck_competitor_products()

def test_recheck_competitor_scraping_suspended(setup_env, monkeypatch):
    monitor_tasks = setup_env

    monkeypatch.setattr(monitor_tasks, "is_scraping_suspended", lambda: True)
    monitor_tasks.recheck_competitor_products()

def test_recheck_competitor_dispatch_limit_exceeded(setup_env):
    monitor_tasks = setup_env

    monitor_tasks.competitor_dispatch_limiter.allow_request = lambda *a, **k: False
    monitor_tasks.recheck_competitor_products()

def test_recheck_competitor_calls_collect(setup_env, monkeypatch):
    monitor_tasks = setup_env

    monkeypatch.setattr(monitor_tasks.circuit_breaker, "allow_request", lambda *a, **k: True)
    monitor_tasks.redis_client = DummyRedis()
    monitor_tasks.competitor_dispatch_limiter.allow_request = lambda *a, **k: True

    fake_products = [
        Mock(product_url="c1", monitored_product_id="m1"),
        Mock(product_url="c2", monitored_product_id="m2")
    ]
    monkeypatch.setattr(monitor_tasks, "get_all_competitor_products", lambda *a, **k: fake_products)

    called = []
    class FakeTask:
        @staticmethod
        def delay(monitored_id=None, url=None, **k):
            called.append((monitored_id, url))

    monkeypatch.setattr(monitor_tasks, "collect_competitor_task", FakeTask)
    monitor_tasks.recheck_competitor_products()

    assert called == [
        ("m1", "c1"),
        ("m2", "c2")
    ]
