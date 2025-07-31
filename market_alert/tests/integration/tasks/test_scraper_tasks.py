"""Testes das tarefas de scraping executadas pelo Celery."""
import pytest
import pickle
from fastapi import HTTPException

from app.exceptions import ScraperError
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

from app.tasks.scraper_tasks import collect_product_task, collect_competitor_task, adaptive_recheck
from tests.integration.tasks.test_monitor_tasks import DummyCompare

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
    """ Quando o payload é inválido (Pydantic), a task capturar erro, registrar falha """
    #Chama a task direto via .run
    result = collect_product_task.run(
        "https://mercadolivre.com.br/abc",
        VALID_UUID,
        "Nome Produto",
        "not-a-decimal"
    )
    assert result is None

def test_collect_product_task_scraping_http_exception(monkeypatch):
    """ Mocka scrape_monitored_product para lançar HTTPException e confirma que ela é propaganda """
    def raise_http_exception(*args, **kwargs):
        raise HTTPException(status_code=429)

    monkeypatch.setattr("app.tasks.scraper_tasks.scrape_monitored_product", raise_http_exception)
    monkeypatch.setattr("app.tasks.scraper_tasks.SessionLocal", lambda: DummySession())
    monkeypatch.setattr("app.tasks.scraper_tasks.get_monitored_product_by_id", lambda db, pid: None)
    monkeypatch.setattr("app.tasks.scraper_tasks.get_latest_comparisons", lambda db, pid, limit=3: [])

    captured = {}
    def fake_create(db, product_id, url, message, error_type):
        captured["args"] = (str(product_id), url, message, error_type)

    monkeypatch.setattr("app.tasks.scraper_tasks.crud_errors.create_scraping_error", fake_create)

    with pytest.raises(ScraperError) as exc:
        collect_product_task.run(
            "https://mercadolivre.com.br/abc",
            VALID_UUID,
            "Produto A",
            99.0,
            VALID_UUID
        )
    assert exc.value.status_code == 429
    assert captured["args"][0] == VALID_UUID
    assert captured["args"][1] == "https://mercadolivre.com.br/abc"

def test_scraper_error_is_picklable():
    err = ScraperError(status_code=400, detail="bad")
    dump = pickle.dumps(err)
    loaded = pickle.loads(dump)
    assert isinstance(loaded, ScraperError)
    assert loaded.status_code == 400
    assert loaded.detail == "bad"

def test_collect_product_task_rate_limited(monkeypatch):
    """ Se monitored_rate_limiter.allow_request retornar False, a task captura erro, registrar falha """
    monkeypatch.setattr(
        "app.tasks.scraper_tasks.RateLimiter.allow_request",
        lambda self: False
    )

    result = collect_product_task.run(
        "https://mercadolivre.com.br/abc",
        VALID_UUID,
        "Produto B",
        50.0
    )
    assert result is None

def test_collect_product_task_generic_exception_creates_error(monkeypatch):
    def raise_exc(*a, **k):
        raise Exception("boom")

    captured = {}

    monkeypatch.setattr("app.tasks.scraper_tasks.scrape_monitored_product", raise_exc)
    monkeypatch.setattr("app.tasks.scraper_tasks.SessionLocal", lambda: DummySession())
    monkeypatch.setattr("app.tasks.scraper_tasks.get_monitored_product_by_id", lambda db, pid: None)
    monkeypatch.setattr("app.tasks.scraper_tasks.get_latest_comparisons", lambda db, pid, limit=3: [])

    def fake_create(db, product_id, url, message, error_type):
        captured["args"] = (str(product_id), url, message, error_type)

    monkeypatch.setattr("app.tasks.scraper_tasks.crud_errors.create_scraping_error", fake_create)

    collect_product_task.run(
        "https://ml.com/x",
        VALID_UUID,
        "Prod",
        99.0,
        VALID_UUID
    )

    assert captured["args"][0] == VALID_UUID
    assert captured["args"][1] == "https://ml.com/x"


def test_collect_competitor_task_invalid_payload():
    """ Quando o payload é invalido (Pydantic), a task deve registrar falha e não lançar exceção """
    result = collect_competitor_task.run(
        "not-a-uuid",
        "https://mercadolivre.com.br/comp",
    )
    assert result is None

def test_collect_competitor_task_scraping_http_exception(monkeypatch):
    """ scrape_competitor_product lança HTTPException, registra erro e retorna HTTPException """
    def raise_http_exception(*args, **kwargs):
        raise HTTPException(status_code=429)

    monkeypatch.setattr("app.tasks.scraper_tasks.scrape_competitor_product", raise_http_exception)
    monkeypatch.setattr("app.tasks.scraper_tasks.SessionLocal", lambda: DummySession())
    monkeypatch.setattr("app.tasks.scraper_tasks.get_monitored_product_by_id", lambda db, pid: None)
    monkeypatch.setattr("app.tasks.scraper_tasks.get_latest_comparisons", lambda db, pid, limit=3: [])

    captured = {}
    def fake_create(db, product_id, url, message, error_type):
        captured["args"] = (str(product_id), url, message, error_type)

    monkeypatch.setattr("app.tasks.scraper_tasks.crud_errors.create_scraping_error", fake_create)

    with pytest.raises(ScraperError) as exc:
        collect_competitor_task.run(
            VALID_UUID,
            "https://mercadolivre.com.br/comp"
        )
    assert exc.value.status_code == 429
    assert captured["args"][0] == VALID_UUID
    assert captured["args"][1] == "https://mercadolivre.com.br/comp"


def test_collect_competitor_task_rate_limited(monkeypatch):
    """ Se o competitor_rate_limiter não permitir, a task encerra sem scraping """
    monkeypatch.setattr(
        "app.tasks.scraper_tasks.RateLimiter.allow_request",
        lambda self: False
    )

    result = collect_competitor_task.run(
        VALID_UUID,
        "https://mercadolivre.com.br/comp"
    )
    assert result is None

def test_collect_product_task_schedules_next(monkeypatch):
    """ Após execução bem-sucedida, deve agendar próxima checagem """
    prod = SimpleNamespace(
        id=VALID_UUID,
        product_url="https://ml.com/p1",
        user_id=VALID_UUID,
        name_identification="Prod",
        target_price=10.0
    )
    comparisons = [SimpleNamespace(id="c1")]

    monkeypatch.setattr("app.tasks.scraper_tasks.scrape_monitored_product", lambda *a, **k: {"product_id": prod.id})
    monkeypatch.setattr("app.tasks.scraper_tasks.SessionLocal", DummySession)
    monkeypatch.setattr("app.tasks.scraper_tasks.get_monitored_product_by_id", lambda db, pid: prod)
    monkeypatch.setattr("app.tasks.scraper_tasks.get_latest_comparisons", lambda db, pid, limit=3: comparisons)
    monkeypatch.setattr(adaptive_recheck, "redis", type("FR", (), {"get": lambda *a, **k: None, "set": lambda *a, **k: None, "delete": lambda *a, **k: None})())

    called = {}

    def fake_schedule(p, comps):
        called["args"] = (p, comps)
        return datetime.now(timezone.utc) + timedelta(seconds=60)

    monkeypatch.setattr(adaptive_recheck, "schedule_next", fake_schedule)
    monkeypatch.setattr(collect_product_task, "apply_async", lambda *a, **k: None)

    collect_product_task.run(
        prod.product_url,
        prod.user_id,
        prod.name_identification,
        prod.target_price
    )

    assert called["args"] == (prod, comparisons)

def test_collect_competitor_task_schedules_next(monkeypatch):
    """ Fluxo de sucesso agenda próxima coleta de concorrente """
    prod = SimpleNamespace(
        id=VALID_UUID,
        product_url="https://m1.com/p1",
        user_id=VALID_UUID,
        name_identification="Prod",
        target_price=10.0
    )
    comparisons = [SimpleNamespace(id="c1")]

    monkeypatch.setattr("app.tasks.scraper_tasks.scrape_competitor_product", lambda *a, **k: None)
    monkeypatch.setattr("app.tasks.scraper_tasks.SessionLocal", DummySession)
    monkeypatch.setattr("app.tasks.scraper_tasks.get_monitored_product_by_id", lambda db, pid: prod)
    monkeypatch.setattr("app.tasks.scraper_tasks.get_latest_comparisons", lambda db, pid, limit=3: comparisons)
    monkeypatch.setattr("app.tasks.scraper_tasks.compare_prices_task", DummyCompare)
    monkeypatch.setattr(adaptive_recheck, "redis", type("FR", (), {"get": lambda *a, **k: None, "set": lambda *a, **k: None, "delete": lambda *a, **k: None})())

    called = {}

    def fake_schedule(p, comps):
        called["args"] = (p, comps)
        return datetime.now(timezone.utc) + timedelta(seconds=60)

    monkeypatch.setattr(adaptive_recheck, "schedule_next", fake_schedule)
    monkeypatch.setattr(collect_competitor_task, "apply_async", lambda *a, **k: None)

    collect_competitor_task.run(
        prod.id,
        "https://ml.com/c1"
    )

    assert called["args"] == (prod, comparisons)
