""" Testes unitários das tasks de scraping sem dependências externas """

from types import SimpleNamespace

import pytest

from shared.schemas.schemas_scraper import ScrapeResult

from market_alert.tasks.scraper_tasks import (
    _compute_retry_delay,
    _result_price_changed,
    _result_product_id,
    _result_status,
    collect_competitor_task,
    collect_product_task,
    redis_client,
)


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

    collect_product_task.run("http://produto", VALID_UUID, "Produto")

    assert chamado["url"] == "http://produto"
    assert chamado["user_id"] == VALID_UUID
    assert chamado["payload"].name_identification == "Produto"

def test_collect_product_task_accepts_missing_name(monkeypatch):
    """ Garante que o payload não falha quando o nome está ausente """
    chamado = {}

    def fake_service(db, url, user_id, payload):
        chamado["payload"] = payload
        return {"status": "success", "product_id": "xyz"}

    monkeypatch.setattr("market_alert.tasks.scraper_tasks.scrape_monitored_product", fake_service)
    monkeypatch.setattr("market_alert.tasks.scraper_tasks.SessionLocal", lambda: DummySession())
    monkeypatch.setattr("market_alert.tasks.scraper_tasks.redis_client.set", lambda *a, **k: None)

    collect_product_task.run("http://produto", VALID_UUID, None)

    assert chamado["payload"].name_identification is None

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

def test_result_helpers_accept_result_and_mapping():
    """Garante compatibilidade com ``ScrapeResult`` e dicionários legados."""

    #O contrato compartilhado retorna ``ScrapeResult`` diretamente
    result = ScrapeResult(status="success", product_id="xyz", price_changed=False)

    assert _result_status(result) == "success"
    assert _result_product_id(result) == "xyz"
    assert _result_price_changed(result) is False

    #Cenário legado onde a task recebe um mapeamento simples
    legacy_mapping = {"status": "not_modified", "product_id": "abc"}

    assert _result_status(legacy_mapping) == "not_modified"
    assert _result_product_id(legacy_mapping) == "abc"
    assert _result_price_changed(legacy_mapping) is False


def test_result_price_changed_defaults_by_status():
    """Sem flag explícita, o status ``success`` implica alteração de preço."""

    assert _result_price_changed({"status": "success"}) is True
    assert _result_price_changed({"status": "no_result"}) is False
    assert _result_status({}) == "unknown"


def test_compute_retry_delay_caps_maximum():
    """Confere limite superior aplicado ao backoff exponencial."""

    #Para a primeira tentativa o valor deve ser igual à base
    assert _compute_retry_delay(base=30, attempt=1, limit=120) == 30

    #Tentativas posteriores devem respeitar o teto configurado
    assert _compute_retry_delay(base=30, attempt=3, limit=90) == 90
    