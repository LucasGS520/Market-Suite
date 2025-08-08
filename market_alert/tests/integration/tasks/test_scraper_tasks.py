""" Testes de integração das tasks de scraping usando o serviço externo market_scraper """

import pickle
from types import SimpleNamespace

import pytest
import requests

from market_alert.exceptions import ScraperError
from alert_app.tasks.scraper_tasks import collect_product_tasks, collect_competitor_tasks


class DummySession:
    """ Gerente de contexto simples emulando uma sessão SQLAlchemy """
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        pass

#UUID válido fixo para testes
VALID_UUID = "123e4567-e89b-12d3-a456-426655440000"

def test_collect_product_tasks_with_invalid_payload():
    """ Quando o payload é inválido (Pydantic), a task encerra sem exceção """
    result = collect_product_task.run(
        "https://mercadolivre.com.br/abc",
        VALID_UUID,
        "Nome Produto",
        "not-a-decimal",
    )
    assert result is None

def test_collect_product_task_scraping_http_exception(monkeypatch):
    """ Simula falha HTTP ao chamar o serviço externo e verifica a exceção """

    def fake_post(*args, **kwargs):
        resp = SimpleNamespace(status_code=429)
        raise requests.RequestException(response=resp)

    monkeypatch.setattr("alert_app.tasks.scraper_tasks.requests.post", fake_post)
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.SessionLocal", lambda: DummySession())

    with pytest.raises(ScraperError) as exc:
        collect_product_task.run(
            "https://mercadolivre.com.br/abc",
            VALID_UUID,
            "Produto A",
            99.0,
        )
    assert exc.value.status_code == 429

def test_scraper_error_is_picklable():
    """ Garante que o ScraperError pode ser serializado pelo Celery """
    err = ScraperError(status_code=400, detail="bad")
    dump = pickle.dumps(err)
    loaded = pickle.loads(dump)
    assert isinstance(loaded, ScraperError)
    assert loaded.status_code == 400
    assert loaded.detail == "bad"

def test_collect_product_task_generic_exception_creates_error(monkeypatch):
    """ Falhas genéricas na persistência devem gerar registro de erro """

    def fake_post(*a, **k):
        return SimpleNamespace(
            json=lambda: {"current_price": 10},
            raise_for_status=lambda: None,
        )

    captured = {}

    def fake_persist(db, user_id, product_data, scraped_info, last_checked):
        raise Exception("boom")

    def fake_create(db, product_id, url, message, error_type):
        captured["args"] = (str(product_id), url, message, error_type)

    monkeypatch.setattr("alert_app.tasks.scraper_tasks.requests.post", fake_post)
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.SessionLocal", lambda: DummySession())
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.create_or_update_monitored_product_scraped", fake_persist)
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.crud_errors.create_scraping_error", fake_create)

    collect_product_task.run(
        "https://ml.com/x",
        VALID_UUID,
        "Prod",
        99.0,
        VALID_UUID,
    )

    assert captured["args"][0] == VALID_UUID
    assert captured["args"][1] == "https://ml.com/x"


def test_collect_competitor_task_invalid_payload():
    """ Quando o payload é invalido, a task deve encerrar sem exceção """
    result = collect_competitor_task.run(
        "not-a-uuid",
        "https://mercadolivre.com.br/comp",
    )
    assert result is None

def test_collect_competitor_task_scraping_http_exception(monkeypatch):
    """ Erro HTTP no serviço externo deve ser propagado como ScraperError """

    def fake_post(*a, **k):
        resp = SimpleNamespace(status_code=500)
        raise requests.RequestException(response=resp)

    monkeypatch.setattr("alert_app.tasks.scraper_tasks.requests.post", fake_post)
    monkeypatch.setattr("alert_app.tasks.scraper_tasks.SessionLocal", lambda: DummySession())

    with pytest.raises(ScraperError):
        collect_competitor_task.run(
            VALID_UUID,
            "https://mercadolivre.com.br/comp",
        )
