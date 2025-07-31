import pytest
from unittest.mock import Mock
from uuid import uuid4
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.services.services_scraper_competitor import scrape_competitor_product
from app.schemas.schemas_products import CompetitorProductCreateScraping


class DummyRedis:
    def get(self, *a, **k):
        return None

    def set(self, *a, **k):
        pass

    def exists(self, *a, **k):
        return False

class FakeRobots:
    def get_crawl_delay(self, user_agent="*"):
        return None

def _patch_common(monkeypatch):
    module = "app.services.services_scraper_competitor"
    monkeypatch.setattr("app.services.services_scraper_common.RobotsTxtParser", lambda *a, **k: FakeRobots())
    monkeypatch.setattr(
        f"{module}.create_or_update_competitor_product_scraped",
        lambda *a, **k: None,
        raising=False
    )
    monkeypatch.setattr("app.services.services_scraper_common.HumanizedDelayManager.wait", lambda self, *a, **k: None)
    class DummyRecovery:
        async def handle_block(self, *a, **k):
            pass

    monkeypatch.setattr("app.services.services_scraper_common.BlockRecoveryManager", lambda *a, **k: DummyRecovery())
    redis = DummyRedis()
    monkeypatch.setattr("app.services.services_scraper_common.redis_client", redis, raising=False)
    monkeypatch.setattr("app.utils.circuit_breaker.get_redis_client", lambda: redis)

def _payload():
    return CompetitorProductCreateScraping(
        competitor_id=str(uuid4()),
        monitored_product_id=str(uuid4()),
        product_url="https://example.com/item"
    )

def test_not_product_page_raises_bad_request(monkeypatch):
    _patch_common(monkeypatch)
    redis = DummyRedis()
    monkeypatch.setattr(
        "app.services.services_scraper_competitor.redis_client",
        redis,
        raising=False
    )
    monkeypatch.setattr("app.utils.redis_client.get_redis_client", lambda: redis)
    import app.services.services_cache_scraper as cache_scraper

    monkeypatch.setattr(cache_scraper.cache_manager, "redis", redis)

    html = "<html><body><p>sem produto</p></body></html>"
    async def fake_playwright(url: str):
        return html

    monkeypatch.setattr("app.services.services_scraper_common.fetch_html_playwright", fake_playwright)
    monkeypatch.setattr("app.services.services_scraper_common.parser.looks_like_product_page", lambda _html: False)

    called = {"parse": False}

    def fake_parse(*a, **k):
        called["parse"] = True
        return {}

    monkeypatch.setattr(
        "app.services.services_scraper_common.parser.parse_product_details",
        fake_parse
    )

    payload = _payload()

    with pytest.raises(HTTPException) as exc:
        scrape_competitor_product(
            db=Mock(spec=Session),
            url=payload.product_url,
            user_id=uuid4(),
            payload=payload
        )

    assert exc.value.status_code == 400
    assert called["parse"] is False
