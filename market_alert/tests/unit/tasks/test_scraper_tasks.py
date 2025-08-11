""" Testes unitários das tasks de scraping com mocks do serviço market_scraper """

from decimal import Decimal
from types import SimpleNamespace

import pytest
import sys
from market_alert import exceptions as base_exceptions

sys.modules.setdefault("market_alert.exceptions", base_exceptions)
import types

#Cria pacotes fictícios necessários para a importação das tasks
sys.modules.setdefault("market_scraper.utils.constants", types.SimpleNamespace(PRODUCT_HOSTS=[]))
sys.modules.setdefault("market_scraper.utils.playwright_client", types.SimpleNamespace())

import importlib
import market_alert  # type: ignore
import types
sys.modules.setdefault("market_scraper.utils", types.ModuleType("market_scraper.utils"))
ms_utils = sys.modules["market_scraper.utils"]

# Mapeia utilitários reais sob o namespace esperado pelos testes
sys.modules.setdefault("market_alert.utils", types.ModuleType("market_alert.utils"))
market_alert.utils = sys.modules["market_alert.utils"]
sys.modules.setdefault("market_scraper.utils.logging_utils", types.SimpleNamespace(mask_identifier=lambda x: x))
sys.modules.setdefault("market_scraper.utils.comparator", types.SimpleNamespace(compare_prices=lambda *a, **k: None))
sys.modules.setdefault("market_alert.utils.redis_client", importlib.import_module("utils.redis_client"))
sys.modules.setdefault("market_alert.utils.circuit_breaker", types.SimpleNamespace(get_redis_client=lambda: None))
sys.modules.setdefault("market_alert.utils.robots_txt", types.SimpleNamespace(requests=types.SimpleNamespace(get=lambda *a, **k: type("Resp", (), {"status_code": 200, "text": ""})()), get_redis_client=lambda: None))
sys.modules.setdefault("market_alert.utils.intelligent_cache", types.SimpleNamespace(get_redis_client=lambda: None))

market_alert.utils.logging_utils = sys.modules["market_scraper.utils.logging_utils"]
market_alert.utils.comparator = sys.modules["market_scraper.utils.comparator"]
ms_utils.mask_identifier = lambda x: x
market_alert.utils.redis_client = sys.modules["market_alert.utils.redis_client"]
market_alert.utils.circuit_breaker = sys.modules["market_alert.utils.circuit_breaker"]
market_alert.utils.robots_txt = sys.modules["market_alert.utils.robots_txt"]
market_alert.utils.intelligent_cache = sys.modules["market_alert.utils.intelligent_cache"]

services_pkg = types.ModuleType("market_alert.services")
sys.modules.setdefault("market_alert.services", services_pkg)
sys.modules.setdefault("market_alert.services.services_scraper_common", types.SimpleNamespace(redis_client=None, CircuitBreaker=lambda: None))
sys.modules.setdefault("market_alert.services.services_cache_scraper", types.SimpleNamespace(cache_manager=types.SimpleNamespace(redis=None)))
sys.modules.setdefault("market_alert.services.services_comparison", types.SimpleNamespace(run_price_comparison=lambda *a, **k: None))
setattr(market_alert, "services", services_pkg)
services_pkg.services_scraper_common = sys.modules["market_alert.services.services_scraper_common"]
services_pkg.services_cache_scraper = sys.modules["market_alert.services.services_cache_scraper"]
services_pkg.services_comparison = sys.modules["market_alert.services.services_comparison"]

from market_alert.tasks.scraper_tasks import collect_product_task, collect_competitor_task


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

    monkeypatch.setattr("market_alert.tasks.scraper_tasks.scraper_client.parse", fake_parse)
    monkeypatch.setattr("market_alert.tasks.scraper_tasks.SessionLocal", lambda: DummySession())
    monkeypatch.setattr("market_alert.tasks.scraper_tasks.create_or_update_monitored_product_scraped", fake_persist)
    monkeypatch.setattr("market_alert.tasks.scraper_tasks.compare_prices_task.delay", lambda pid: chamado.setdefault("compare", pid))
    monkeypatch.setattr("market_alert.tasks.scraper_tasks.redis_client.set", lambda *a, **k: None)

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

    monkeypatch.setattr("market_alert.tasks.scraper_tasks.scraper_client.parse", fake_parse)
    monkeypatch.setattr("market_alert.tasks.scraper_tasks.SessionLocal", lambda: DummySession())
    monkeypatch.setattr("market_alert.tasks.scraper_tasks.create_or_update_competitor_product_scraped", fake_persist)
    monkeypatch.setattr("market_alert.tasks.scraper_tasks.compare_prices_task.delay", lambda pid: chamado.setdefault("compare", pid))

    collect_competitor_task.run(VALID_UUID, "http://concorrente")

    assert chamado["url"] == "http://concorrente"
    assert chamado["product_type"] == "competitor"
    assert str(chamado["persist"]["monitored_id"]) == VALID_UUID
    assert chamado["compare"] == VALID_UUID
