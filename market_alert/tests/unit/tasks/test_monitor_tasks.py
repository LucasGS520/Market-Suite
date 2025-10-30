""" Testes das rotinas periódicas de monitoramento """

from types import SimpleNamespace
from uuid import UUID
import time

import pytest

from market_alert.scraper.types import ScrapeResult
from market_alert.scraper.scraper_client import ScraperClientError
from market_alert.tasks import monitor_tasks


class DummySession:
    """ Contexto de sessão fictício """
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

class DummyProduct:
    """ Estrutura mínima para simular produtos monitorados """

    def __init__(self, product_id: UUID, user_id: UUID, url: str, name: str):
        self.id = product_id
        self.user_id = user_id
        self.product_url = url
        self.name_identification = name
        self.target_price = 0


class DummyCompetitor:
    """ Estrutura mínima para simular concorrentes """

    def __init__(self, competitor_id: UUID, monitored_id: UUID, url: str):
        self.id = competitor_id
        self.monitored_product_id = monitored_id
        self.product_url = url
        self.monitored_product = SimpleNamespace(user_id=monitored_id)

@pytest.mark.parametrize(
    "task,key",
    [
        (monitor_tasks.recheck_monitored_products, "beat:last_scraping"),
        (monitor_tasks.recheck_competitor_products, "beat:last_competitor"),
    ],
)
def test_heartbeat_expire(monkeypatch, fake_redis_client, task, key):
    """ Garante que o heartbeat criado expira automaticamente no Redis """
    fake_redis = fake_redis_client

    monkeypatch.setattr(monitor_tasks, "HEARTBEAT_TTL_SECONDS", 1)
    monkeypatch.setattr(monitor_tasks, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(monitor_tasks, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(monitor_tasks, "get_products_by_type", lambda db, mt: [])
    monkeypatch.setattr(monitor_tasks, "get_all_competitor_products", lambda db: [])
    monkeypatch.setattr(monitor_tasks, "_collect_batch_products", lambda *a, **k: "success")
    monkeypatch.setattr(monitor_tasks, "_collect_batch_competitors", lambda *a, **k: ("success", set()))
    monkeypatch.setattr(monitor_tasks, "compare_prices_task", SimpleNamespace(delay=lambda *a, **k: None))
    monkeypatch.setattr(
        monitor_tasks,
        "SCRAPING_LATENCY_SECONDS",
        SimpleNamespace(labels=lambda **k: SimpleNamespace(observe=lambda x: None)),
    )

    tempo = [0]
    monkeypatch.setattr(time, "time", lambda: tempo[0])

    task.run()
    assert fake_redis.exists(key)

    tempo[0] = 2
    assert fake_redis.get(key) is None
    assert not fake_redis.exists(key)

def test_recheck_monitored_products_no_result_retry(monkeypatch):
    """ Verifica que ``no_result`` persiste erro e agenda retry """

    dummy_id = UUID("123e4567-e89b-12d3-a456-426655440000")
    product = DummyProduct(dummy_id, dummy_id, "http://produto", "Produto")

    called = {}

    def fake_retry(*, countdown):
        called["countdown"] = countdown
        raise RuntimeError("retry")

    monkeypatch.setattr(monitor_tasks, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(monitor_tasks, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(monitor_tasks, "get_products_by_type", lambda db, mt: [product])
    monkeypatch.setattr(monitor_tasks, "redis_client", SimpleNamespace(set=lambda *a, **k: None))
    monkeypatch.setattr(monitor_tasks.recheck_monitored_products, "retry", fake_retry)

    def fake_scrape(*args, **kwargs):
        return ScrapeResult(status="no_result", product_id=str(dummy_id), http_status=422)

    created = {}

    def fake_create(db, product_id, url, message, error_type):
        created["product_id"] = product_id
        created["url"] = url
        created["error_type"] = error_type

    monkeypatch.setattr(monitor_tasks, "scrape_monitored_product", fake_scrape)
    monkeypatch.setattr(monitor_tasks.crud_errors, "create_scraping_error", fake_create)

    with pytest.raises(RuntimeError):
        monitor_tasks.recheck_monitored_products.run()

    expected = min(
        monitor_tasks.settings.SCRAPER_NO_RESULT_RETRY_SECONDS,
        monitor_tasks.settings.SCRAPER_MAX_RETRY_DELAY_SECONDS,
    )
    assert called["countdown"] == expected
    assert created["product_id"] == dummy_id
    assert created["url"] == "http://produto"
    assert created["error_type"].value == "no_result"


def test_recheck_monitored_products_handles_429(monkeypatch):
    """ Confere suspensão temporária e retry quando o scraper devolve 429 """

    dummy_id = UUID("123e4567-e89b-12d3-a456-426655440001")
    product = DummyProduct(dummy_id, dummy_id, "http://produto", "Produto")

    suspend_called = {}

    def fake_suspend(seconds):
        suspend_called["seconds"] = seconds

    def fake_retry(*, countdown):
        suspend_called["countdown"] = countdown
        raise RuntimeError("retry")

    monkeypatch.setattr(monitor_tasks, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(monitor_tasks, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(monitor_tasks, "get_products_by_type", lambda db, mt: [product])
    monkeypatch.setattr(monitor_tasks, "redis_client", SimpleNamespace(set=lambda *a, **k: None))
    monkeypatch.setattr(monitor_tasks, "suspend_scraping", fake_suspend)
    monkeypatch.setattr(monitor_tasks.recheck_monitored_products, "retry", fake_retry)

    def fake_scrape(*args, **kwargs):
        raise ScraperClientError("limite", status_code=429, retry_after=30)

    created = {}

    def fake_create(db, product_id, url, message, error_type):
        created.setdefault("calls", []).append((product_id, url, error_type))

    monkeypatch.setattr(monitor_tasks, "scrape_monitored_product", fake_scrape)
    monkeypatch.setattr(monitor_tasks.crud_errors, "create_scraping_error", fake_create)

    with pytest.raises(RuntimeError):
        monitor_tasks.recheck_monitored_products.run()

    assert suspend_called["seconds"] == 30
    assert suspend_called["countdown"] == 30
    assert created["calls"][0][2].value == "http_error"


def test_recheck_monitored_products_handles_robots_block(monkeypatch):
    """ Garante que bloqueios de robots registram métrica sem retry """

    dummy_id = UUID("123e4567-e89b-12d3-a456-426655440002")
    product = DummyProduct(dummy_id, dummy_id, "http://produto", "Produto")

    monkeypatch.setattr(monitor_tasks, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(monitor_tasks, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(monitor_tasks, "get_products_by_type", lambda db, mt: [product])
    monkeypatch.setattr(monitor_tasks, "redis_client", SimpleNamespace(set=lambda *a, **k: None))

    counter = {"inc": 0}

    monkeypatch.setattr(monitor_tasks, "SCRAPER_HEAD_FAILURES_TOTAL", SimpleNamespace(inc=lambda: counter.__setitem__("inc", counter["inc"] + 1)))

    def fake_scrape(*args, **kwargs):
        raise ScraperClientError("robots", status_code=451)

    created = {}

    def fake_create(db, product_id, url, message, error_type):
        created["error_type"] = error_type

    monkeypatch.setattr(monitor_tasks, "scrape_monitored_product", fake_scrape)
    monkeypatch.setattr(monitor_tasks.crud_errors, "create_scraping_error", fake_create)

    monitor_tasks.recheck_monitored_products.run()

    assert counter["inc"] == 1
    assert created["error_type"].value == "http_error"


def test_recheck_competitor_products_retry_on_5xx(monkeypatch):
    """ Valida retry exponencial para erros 5xx em concorrentes """

    monitored_id = UUID("123e4567-e89b-12d3-a456-426655440010")
    competitor = DummyCompetitor(UUID("123e4567-e89b-12d3-a456-426655440011"), monitored_id, "http://concorrente")

    def fake_retry(*, countdown):
        raise RuntimeError("retry")

    monkeypatch.setattr(monitor_tasks, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(monitor_tasks, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(monitor_tasks, "get_all_competitor_products", lambda db: [competitor])
    monkeypatch.setattr(monitor_tasks, "redis_client", SimpleNamespace(set=lambda *a, **k: None))
    monkeypatch.setattr(monitor_tasks.recheck_competitor_products, "retry", fake_retry)
    monkeypatch.setattr(monitor_tasks.crud_errors, "create_scraping_error", lambda *a, **k: None)

    def fake_scrape(*args, **kwargs):
        raise ScraperClientError("erro", status_code=503)

    monkeypatch.setattr(monitor_tasks, "scrape_competitor_product", fake_scrape)

    with pytest.raises(RuntimeError):
        monitor_tasks.recheck_competitor_products.run()
        