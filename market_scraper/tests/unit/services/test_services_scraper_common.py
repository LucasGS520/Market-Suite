import pytest
from unittest.mock import Mock
from uuid import uuid4
from decimal import Decimal
from fastapi import HTTPException

from app.services.services_scraper_monitored import scrape_monitored_product
from app.services.services_scraper_competitor import scrape_competitor_product
from app.schemas.schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping


def _patch_common(monkeypatch):
    class DummyRedis:
        def get(self, *a, **k):
            return None

        def set(self, *a, **k):
            pass

    class DummyRobots:
        def get_crawl_delay(self, user_agent="*"):
            return None

    class DummyCB:
        def allow_request(self, *a, **k):
            return True

        def record_success(self, *a, **k):
            pass

        def record_failure(self, *a, **k):
            pass

    class DummyRecovery:
        async def handle_block(self, *a, **k):
            pass

    monkeypatch.setattr("alert_app.services.services_scraper_common.RobotsTxtParser", lambda *a, **k: DummyRobots())
    monkeypatch.setattr("alert_app.services.services_scraper_common.CircuitBreaker", lambda: DummyCB())
    monkeypatch.setattr("alert_app.services.services_scraper_common.ThrottleManager.wait", lambda self, identifier=None, circuit_key="": None)
    monkeypatch.setattr("alert_app.services.services_scraper_common.ThrottleManager.backoff", lambda self, attempt, circuit_key="": None)
    monkeypatch.setattr("alert_app.services.services_scraper_common.HumanizedDelayManager.wait", lambda self, *a, **k: None)
    monkeypatch.setattr("alert_app.services.services_scraper_common.BlockRecoveryManager", lambda *a, **k: DummyRecovery())

    redis = DummyRedis()
    monkeypatch.setattr("alert_app.services.services_scraper_common.redis_client", redis, raising=False)
    monkeypatch.setattr("alert_app.services.services_scraper_monitored.redis_client", redis, raising=False)
    monkeypatch.setattr("alert_app.services.services_scraper_competitor.redis_client", redis, raising=False)
    monkeypatch.setattr("alert_app.utils.redis_client.get_redis_client", lambda: redis)
    import app.services.services_cache_scraper as cache_scraper
    monkeypatch.setattr(cache_scraper.cache_manager, "redis", redis)
    monkeypatch.setattr("alert_app.services.services_scraper_common.ua_manager.get_user_agent", lambda *a, **k: "UA")
    monkeypatch.setattr("alert_app.services.services_scraper_common.parser.looks_like_product_page", lambda html: True)
    monkeypatch.setattr("alert_app.services.services_scraper_common.parser.parse_product_details", lambda *a, **k: {
        "name": "prod",
        "current_price": "R$ 1,00",
        "old_price": None,
        "thumbnail": None,
        "shipping": "Frete Grátis",
        "seller": None
    })
    monkeypatch.setattr("alert_app.services.services_scraper_common.create_or_update_monitored_product_scraped", lambda *a, **k: type("Obj", (), {"id": uuid4()})())
    monkeypatch.setattr("alert_app.services.services_scraper_common.create_or_update_competitor_product_scraped", lambda *a, **k: type("Obj", (), {"id": uuid4()})())
    monkeypatch.setattr("alert_app.tasks.compare_prices_tasks.compare_prices_task.delay", lambda *a, **k: None)
    monkeypatch.setattr("alert_app.services.services_scraper_common.update_cache", lambda *a, **k: None)

def test_playwright_client_used(monkeypatch):
    _patch_common(monkeypatch)

    called = {}

    async def fake_playwright(url: str):
        called["url"] = url
        return "<html></html>"

    monkeypatch.setattr("alert_app.services.services_scraper_common.fetch_html_playwright", fake_playwright)

    payload = MonitoredProductCreateScraping(
        monitored_product_id=str(uuid4()),
        name_identification="Prod",
        product_url="https://example.com/item",
        target_price=Decimal("1.00")
    )

    result = scrape_monitored_product(
        db=Mock(), url=payload.product_url, user_id=uuid4(), payload=payload
    )

    assert result["status"] == "success"
    assert called.get("url") == str(payload.product_url)

def test_playwright_client_used_competitor(monkeypatch):
    _patch_common(monkeypatch)

    called = {}

    async def fake_playwright(url: str):
        called["url"] = url
        return "<html></html>"

    monkeypatch.setattr("alert_app.services.services_scraper_common.fetch_html_playwright", fake_playwright)

    payload = CompetitorProductCreateScraping(
        competitor_id=str(uuid4()),
        monitored_product_id=str(uuid4()),
        product_url="https://example.com/item"
    )

    result = scrape_competitor_product(
        db=Mock(), user_id=uuid4(), url=payload.product_url, payload=payload
    )

    assert result["status"] == "success"
    assert called.get("url") == str(payload.product_url)

def test_fetch_failure_unrecoverable_raises(monkeypatch):
    _patch_common(monkeypatch)

    async def fail_playwright(url: str):
        raise Exception("fail")

    monkeypatch.setattr("alert_app.services.services_scraper_common.fetch_html_playwright", fail_playwright)

    payload = MonitoredProductCreateScraping(
        monitored_product_id=str(uuid4()),
        name_identification="Prod",
        product_url="https://example.com/item",
        target_price=Decimal("1.00")
    )

    with pytest.raises(HTTPException) as exc:
        scrape_monitored_product(
            db=Mock(), url=payload.product_url, user_id=uuid4(), payload=payload
        )

    assert exc.value.status_code == 502

def test_fetch_failure_unrecoverable_competitor(monkeypatch):
    _patch_common(monkeypatch)

    async def fail_playwright(url: str):
        raise Exception("fail")

    monkeypatch.setattr("alert_app.services.services_scraper_common.fetch_html_playwright", fail_playwright)

    payload = CompetitorProductCreateScraping(
        competitor_id=str(uuid4()),
        monitored_product_id=str(uuid4()),
        product_url="https://example.com/item"
    )

    with pytest.raises(HTTPException) as exc:
        scrape_competitor_product(
            db=Mock(), user_id=uuid4(), url=payload.product_url, payload=payload
        )

    assert exc.value.status_code == 502

def test_timeout_triggers_recovery(monkeypatch):
    _patch_common(monkeypatch)

    class SpyRecovery:
        def __init__(self, *a, **k):
            self.called = False

        async def handle_block(self, *a, **k):
            self.called = True
            return "<html></html>"

    recovery = SpyRecovery()
    monkeypatch.setattr("alert_app.services.services_scraper_common.BlockRecoveryManager", lambda *a, **k: recovery)

    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    async def timeout_fetch(url: str):
        raise PlaywrightTimeoutError()

    monkeypatch.setattr("alert_app.services.services_scraper_common.fetch_html_playwright", timeout_fetch)

    payload = MonitoredProductCreateScraping(
        monitored_product_id=str(uuid4()),
        name_identification="Prod",
        product_url="https://example.com/item",
        target_price=Decimal("1.00")
    )

    result = scrape_monitored_product(
        db=Mock(), url=payload.product_url, user_id=uuid4(), payload=payload
    )

    assert result["status"] == "success"
    assert recovery.called
