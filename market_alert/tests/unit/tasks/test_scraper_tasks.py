""" Testes unitários das tasks de scraping com mocks do serviço market_scraper """

from decimal import Decimal
from types import SimpleNamespace

import pytest
import sys
from market_alert import exceptions as base_exceptions

sys.modules.setdefault("alert_app.exceptions", base_exceptions)
import types
sys.modules.setdefault("market_scraper.scraper_app.utils.constants", types.SimpleNamespace(PRODUCT_HOSTS=[]))
sys.modules.setdefault("market_scraper.scraper_app.utils.playwright_client", types.SimpleNamespace())

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

    def fake_post(url, json, timeout):
        chamado["url"] = url
        chamado["json"] = json
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"current_price": "19.9", "thumbnail": "img.jpg", "free_shipping": True},
            raise_for_status=lambda: None,
        )

    def fake_persist(db, user_id, product_data, scraped_info, last_checked):
        chamado["persist"] = {
            "user_id": str(user_id),
            "preco": scraped_info.current_price,
            "thumb": scraped_info.thumbnail,
            "frete": scraped_info.free_shipping,
        }
        return SimpleNamespace(id="xyz")

    monkeypatch.setattr("alert_app.tasks.scraper_tasks.requests.post", fake_post)
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.SessionLocal", lambda: DummySession())
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.create_or_update_monitored_product_scraped", fake_persist)
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.compare_prices_task.delay", lambda pid: chamado.setdefault("compare", pid))
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.redis_client.set", lambda *a, **k: None)

    collect_product_task.run("http://produto", VALID_UUID, "Produto", 20.0)

    assert chamado["url"].endswith("/scraper/parse")
    assert chamado["json"] == {"url": "http://produto", "product_type": "monitored"}
    assert chamado["persist"]["user_id"] == VALID_UUID
    assert chamado["persist"]["preco"] == Decimal("19.9")
    assert chamado["compare"] == "xyz"

def test_collect_competitor_task_send_request_and_persist(monkeypatch):
    """ Confere o POST e a persistência de dados do concorrente """
    chamado = {}

    def fake_post(url, json, timeout):
        chamado["url"] = url
        chamado["json"] = json
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "name": "Comp",
                "current_price": "50.0",
                "old_price": "60.0",
                "thumbnail": "img.jpg",
                "free_shipping": False,
                "seller": "Loja",
            },
            raise_for_status=lambda: None
        )

    def fake_persist(db, product_data, scraped_info, last_checked):
        chamado["persist"] = {
            "monitored_id": product_data.monitored_product_id,
            "preco": scraped_info.current_price,
            "seller": scraped_info.seller,
        }
        return SimpleNamespace()

    monkeypatch.setattr("alert_app.tasks.scraper_tasks.requests.post", fake_post)
    monkeypatch.setattr("alert_app.tasks.scaper_tasks.SessionLocal", lambda: DummySession())
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.create_or_update_competitor_product_scraped", fake_persist)
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.compare_prices_task.delay", lambda pid: chamado.setdefault("compare", pid))

    collect_competitor_task.run(VALID_UUID, "http://concorrente")

    assert chamado["url"].endswith("/scraper/parse")
    assert chamado["json"] == {"url": "http://concorrente", "product_type": "competitor"}
    assert chamado["persist"]["monitored_id"] == VALID_UUID
    assert chamado["compare"] == VALID_UUID
