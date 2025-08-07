"""Testes das tarefas de monitoramento programado."""

import importlib
from unittest.mock import Mock

import pytest

import alert_app.utils.redis_client as _rc_mod
import alert_app.tasks.compare_prices_tasks as _cp_mod


class DummyRedis:
    def get(self, *a, **k):
        return None
    def exists(self, *a, **k):
        return False
    def set(self, *a, **k):
        pass

class DummyCompare:
    @staticmethod
    def delay(*args, **kwargs):
        pass


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """ Recarrega módulo de monitoramento com dependência simuladas """
    monkeypatch.setattr(_rc_mod, "get_redis_client", lambda: DummyRedis())
    monkeypatch.setattr(_cp_mod, "compare_prices_task", DummyCompare)

    monitor_tasks = importlib.reload(importlib.import_module("alert_app.tasks.monitor_tasks"))
    monitor_tasks.redis_client = DummyRedis()
    return monitor_tasks

def test_recheck_monitored_scraping_suspended(setup_env, monkeypatch):
    """ Flag global ativa deve impedir chamadas ao serviço externo """
    monitor_tasks = setup_env

    monkeypatch.setattr(monitor_tasks, "is_scraping_suspended", lambda: True)
    called = []

    def fake_post(*args, **kwargs):
        called.append(kwargs.get("json"))
        class Resp:
            def raise_for_status(self):
                pass
        return Resp()

    monkeypatch.setattr(monitor_tasks.requests, "post", fake_post)
    monitor_tasks.recheck_monitored_products()
    assert called == []

def test_recheck_monitored_call_service(setup_env, monkeypatch):
    """ Quando permitido, deve chamar o market_scraper para cada produto """
    monitor_tasks = setup_env

    fake_products = [
        Mock(id="1", product_url="u1"),
        Mock(id="2", product_url="u2"),
    ]
    monkeypatch.setattr(monitor_tasks, "get_products_by_type", lambda *a, **k: fake_products)
    called = []

    def fake_post(url, json=None, timeout=0):
        called.append(json)
        class Resp:
            def raise_for_status(self):
                pass
        return Resp()

    monkeypatch.setattr(monitor_tasks.requests, "post", fake_post)
    monkeypatch.setattr(monitor_tasks, "is_scraping_suspended", lambda: False)

    monitor_tasks.recheck_monitored_products()
    assert called == [
        {"url": "u1", "product_type": "monitored", "monitored_id": "1"},
        {"url": "u2", "product_type": "monitored", "monitored_id": "2"},
    ]

def test_recheck_competitor_scraping_suspended(setup_env, monkeypatch):
    """ Flag global ativa deve impedir chamadas para concorrentes """
    monitor_tasks = setup_env

    monkeypatch.setattr(monitor_tasks, "is_scraping_suspended", lambda: True)
    called = []

    def fake_post(*args, **kwargs):
        called.append(kwargs.get("json"))
        class Resp:
            def raise_for_status(self):
                pass
        return Resp()

    monkeypatch.setattr(monitor_tasks.requests, "post", fake_post)
    monitor_tasks.recheck_competitor_products()
    assert called == []

def test_recheck_competitor_call_service(setup_env, monkeypatch):
    """ Deve chamar o market_scraper para cada concorrente e agendar comparação """
    monitor_tasks = setup_env

    fake_products = [
        Mock(id="c1", monitored_product_id="m1", product_url="u1"),
        Mock(id="c2", monitored_product_id="m2", product_url="u2"),
    ]
    monkeypatch.setattr(monitor_tasks, "get_all_competitor_products", lambda *a, **k: fake_products)

    called = []
    def fake_post(url, json=None, timeout=0):
        called.append(json)
        class Resp:
            def raise_for_status(self):
                pass
        return Resp()

    compare_calls = []
    class DummyCompareTask:
        @staticmethod
        def delay(mid):
            compare_calls.append(mid)

    monkeypatch.setattr(monitor_tasks.requests, "post", fake_post)
    monkeypatch.setattr(monitor_tasks, "compare_prices_task", DummyCompareTask)
    monkeypatch.setattr(monitor_tasks, "is_scraping_suspended", lambda: False)

    monitor_tasks.recheck_competitor_products()
    assert called == [
        {"url": "u1", "product_type": "competitor", "competitor_id": "c1", "monitored_id": "m1"},
        {"url": "u2", "product_type": "competitor", "competitor_id": "c2", "monitored_id": "m2"},
    ]
    assert compare_calls == ["m1", "m2"]
