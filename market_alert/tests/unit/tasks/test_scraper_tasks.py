""" Testes unitários das tasks de scraping com mocks do serviço market_scraper """

from decimal import Decimal
from types import SimpleNamespace

import pytest
import sys
from market_alert import exceptions as base_exceptions

sys.modules.setdefault("alert_app.exceptions", base_exceptions)
import types

#Cria pacotes fictícios necessários para a importação das tasks
sys.modules.setdefault("market_scraper.scraper_app.utils.constants", types.SimpleNamespace(PRODUCT_HOSTS=[]))
sys.modules.setdefault("market_scraper.scraper_app.utils.playwright_client", types.SimpleNamespace())

import importlib
import alert_app  # type: ignore

# Mapeia utilitários reais sob o namespace esperado pelos testes
sys.modules.setdefault("alert_app.utils", types.ModuleType("alert_app.utils"))
alert_app.utils = sys.modules["alert_app.utils"]
sys.modules.setdefault("alert_app.utils.logging_utils", types.SimpleNamespace(mask_identifier=lambda x: x))
sys.modules.setdefault("alert_app.utils.comparator", types.SimpleNamespace(compare_prices=lambda *a, **k: None))
sys.modules.setdefault("alert_app.utils.redis_client", importlib.import_module("utils.redis_client"))
sys.modules.setdefault("alert_app.utils.circuit_breaker", types.SimpleNamespace(get_redis_client=lambda: None))
sys.modules.setdefault("alert_app.utils.robots_txt", types.SimpleNamespace(requests=types.SimpleNamespace(get=lambda *a, **k: type("Resp", (), {"status_code": 200, "text": ""})()), get_redis_client=lambda: None))
sys.modules.setdefault("alert_app.utils.intelligent_cache", types.SimpleNamespace(get_redis_client=lambda: None))

alert_app.utils.logging_utils = sys.modules["alert_app.utils.logging_utils"]
alert_app.utils.comparator = sys.modules["alert_app.utils.comparator"]
alert_app.utils.redis_client = sys.modules["alert_app.utils.redis_client"]
alert_app.utils.circuit_breaker = sys.modules["alert_app.utils.circuit_breaker"]
alert_app.utils.robots_txt = sys.modules["alert_app.utils.robots_txt"]
alert_app.utils.intelligent_cache = sys.modules["alert_app.utils.intelligent_cache"]

services_pkg = types.ModuleType("alert_app.services")
sys.modules.setdefault("alert_app.services", services_pkg)
sys.modules.setdefault("alert_app.services.services_scraper_common", types.SimpleNamespace(redis_client=None, CircuitBreaker=lambda: None))
sys.modules.setdefault("alert_app.services.services_cache_scraper", types.SimpleNamespace(cache_manager=types.SimpleNamespace(redis=None)))
sys.modules.setdefault("alert_app.services.services_comparison", types.SimpleNamespace(run_price_comparison=lambda *a, **k: None))
setattr(alert_app, "services", services_pkg)
services_pkg.services_scraper_common = sys.modules["alert_app.services.services_scraper_common"]
services_pkg.services_cache_scraper = sys.modules["alert_app.services.services_cache_scraper"]
services_pkg.services_comparison = sys.modules["alert_app.services.services_comparison"]

from alert_app.tasks.scraper_tasks import collect_product_task, collect_competitor_task


class DummySession:
    """ Contexto fictício simulando uma sessão de banco de dados """
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        pass

VALID_UUID = "123e4567-e89b-12d3-a456-426655440000"


def test_collect_product_task_send_request_and_persists(monkeypatch):
    """ Garante que a task envia POST ao scraper e persiste os dados """
    chamado = {}

    def fake_parse(url, product_type, **extra):
        chamado["url"] = url
        chamado["product_type"] = product_type
        chamado["extra"] = extra
        return {"current_price": "19.9", "thumbnail": "img.jpg", "free_shipping": True}

    def fake_persist(db, user_id, product_data, scraped_info, last_checked):
        chamado["persist"] = {
            "user_id": str(user_id),
            "preco": scraped_info.current_price,
            "thumb": scraped_info.thumbnail,
            "frete": scraped_info.free_shipping,
        }
        return SimpleNamespace(id="xyz")

    monkeypatch.setattr("alert_app.tasks.scraper_tasks.scraper_client.parse", fake_parse)
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.SessionLocal", lambda: DummySession())
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.create_or_update_monitored_product_scraped", fake_persist)
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.compare_prices_task.delay", lambda pid: chamado.setdefault("compare", pid))
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.redis_client.set", lambda *a, **k: None)

    collect_product_task.run("http://produto", VALID_UUID, "Produto", 20.0)

    assert chamado["url"] == "http://produto"
    assert chamado["product_type"] == "monitored"
    assert chamado["persist"]["user_id"] == VALID_UUID
    assert chamado["persist"]["preco"] == Decimal("19.9")
    assert chamado["compare"] == "xyz"

def test_collect_competitor_task_send_request_and_persist(monkeypatch):
    """ Confere o POST e a persistência de dados do concorrente """
    chamado = {}

    def fake_post(url, product_type, **extra):
        chamado["url"] = url
        chamado["product_type"] = product_type
        chamado["extra"] = extra
        return {
            "name": "Comp",
            "current_price": "50.0",
            "old_price": "60.0",
            "thumbnail": "img.jpg",
            "free_shipping": False,
            "seller": "Loja",
        }

    def fake_persist(db, product_data, scraped_info, last_checked):
        chamado["persist"] = {
            "monitored_id": product_data.monitored_product_id,
            "preco": scraped_info.current_price,
            "seller": scraped_info.seller,
        }
        return SimpleNamespace()

    monkeypatch.setattr("alert_app.tasks.scraper_tasks.scraper_client.parse", fake_parse)
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.SessionLocal", lambda: DummySession())
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.create_or_update_competitor_product_scraped", fake_persist)
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.compare_prices_task.delay", lambda pid: chamado.setdefault("compare", pid))

    collect_competitor_task.run(VALID_UUID, "http://concorrente")

    assert chamado["url"] == "http://concorrente"
    assert chamado["product_type"] == "competitor"
    assert str(chamado["persist"]["monitored_id"]) == VALID_UUID
    assert chamado["compare"] == VALID_UUID
