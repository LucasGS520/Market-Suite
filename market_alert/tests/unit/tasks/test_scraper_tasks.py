""" Testes unitários das tasks de scraping com mocks do serviço market_scraper """

from types import SimpleNamespace

import pytest
import sys
from shared import exceptions as base_exceptions
from shared.utils.redis_client import get_redis_client

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
sys.modules.setdefault("market_scraper.utils.comparator", types.SimpleNamespace(compare_prices=lambda *a, **k: None))
sys.modules.setdefault("market_alert.utils.redis_client", importlib.import_module("utils.redis_client"))
sys.modules.setdefault("market_alert.utils.circuit_breaker", types.SimpleNamespace(get_redis_client=lambda: None))
sys.modules.setdefault(
    "market_alert.utils.robots_txt",
    types.SimpleNamespace(
        requests=types.SimpleNamespace(
            get=lambda *a, **k: type("Resp", (), {"status_code": 200, "text": ""})()
        ),
        get_redis_client=lambda: None,
    ),
)
sys.modules.setdefault("market_alert.utils.intelligent_cache", types.SimpleNamespace(get_redis_client=lambda: None))

market_alert.utils.comparator = sys.modules["market_scraper.utils.comparator"]
market_alert.utils.redis_client = sys.modules["market_alert.utils.redis_client"]
market_alert.utils.circuit_breaker = sys.modules["market_alert.utils.circuit_breaker"]
market_alert.utils.robots_txt = sys.modules["market_alert.utils.robots_txt"]
market_alert.utils.intelligent_cache = sys.modules["market_alert.utils.intelligent_cache"]

sys.modules.setdefault("market_alert.utils.comparator", sys.modules["market_scraper.utils.comparator"])

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
    """ Garante que a task encaminha os dados ao serviço de scraping """
    chamado = {}

    def fake_service(db, url, user_id, payload):
        chamado["url"] = url
        chamado["user_id"] = str(user_id)
        chamado["payload"] = payload
        return {"status": "success", "product_id": "xyz"}

    monkeypatch.setattr("market_alert.tasks.scraper_tasks.scrape_monitored_product", fake_service)
    monkeypatch.setattr("market_alert.tasks.scraper_tasks.SessionLocal", lambda: DummySession())
    monkeypatch.setattr("market_alert.tasks.scraper_tasks.redis_client.set", lambda *a, **k: None)

    collect_product_task.run("http://produto", VALID_UUID, "Produto", 20.0)

    assert chamado["url"] == "http://produto"
    assert chamado["user_id"] == VALID_UUID
    assert chamado["payload"].name_identification == "Produto"

def test_collect_competitor_task_send_request_and_persist(monkeypatch):
    """ Confere a delegação ao serviço de scraping de concorrentes """
    chamado = {}

    def fake_service(db, user_id, url, payload):
        chamado["url"] = url
        chamado["user_id"] = str(user_id)
        chamado["monitored_id"] = str(payload.monitored_product_id)
        return {"status": "success", "competitor_id": "abc"}

    monkeypatch.setattr("market_alert.tasks.scraper_tasks.scrape_competitor_product", fake_service)
    monkeypatch.setattr("market_alert.tasks.scraper_tasks.SessionLocal", lambda: DummySession())
    monkeypatch.setattr("market_alert.tasks.scraper_tasks.get_monitored_product_by_id", lambda db, pid: SimpleNamespace(user_id=VALID_UUID))
    monkeypatch.setattr("market_alert.tasks.scraper_tasks.compare_prices_task.delay", lambda pid: chamado.setdefault("compare", pid))

    collect_competitor_task.run(VALID_UUID, "http://concorrente")

    assert chamado["url"] == "http://concorrente"
    assert chamado["monitored_id"] == VALID_UUID
    assert chamado["compare"] == VALID_UUID
