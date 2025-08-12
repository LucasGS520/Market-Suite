from unittest.mock import Mock
from uuid import uuid4
from sqlalchemy.orm import Session
from fastapi import HTTPException

from shared.schemas.products import CompetitorProductCreateScraping
import pytest

try:
    from market_alert.services import services_scraper_competitor as mod
    scrape_competitor_product = mod.scrape_competitor_product
except Exception:
    pytestmark = pytest.mark.skip(reason="Dependências do market_alert indisponíveis")


class DummyRedis:
    """ Implementação simples de Redis para uso em testes """
    def get(self, *a, **k):
        return None

    def set(self, *a, **k):
        pass

    def exists(self, *a, **k):
        return False

class FakeRobots:
    """ Simula parser de robots.txt sem restrições """
    def get_crawl_delay(self, user_agent="*"):
        return None

def _patch_common(monkeypatch):
    """ Aplica patches para isolar dependências externas """
    module = mod
    import types, sys
    sys.modules.setdefault("market_scraper.core.config", types.SimpleNamespace(settings=types.SimpleNamespace(CACHE_BASE_TTL=0)))
    monkeypatch.setattr("market_scraper.services.services_scraper_common.RobotsTxtParser", lambda *a, **k: FakeRobots())
    monkeypatch.setattr(
        module,
        "create_or_update_competitor_product_scraped",
        lambda *a, **k: None,
        raising=False
    )
    monkeypatch.setattr("market_scraper.services.services_scraper_common.HumanizedDelayManager.wait", lambda self, *a, **k: None)
    class DummyRecovery:
        async def handle_block(self, *a, **k):
            pass

    monkeypatch.setattr("market_scraper.services.services_scraper_common.BlockRecoveryManager", lambda *a, **k: DummyRecovery())
    redis = DummyRedis()
    monkeypatch.setattr("market_scraper.services.services_scraper_common.redis_client", redis, raising=False)
    monkeypatch.setattr("shared.utils.circuit_breaker.get_redis_client", lambda: redis)

def _payload():
    """ Monta payload padrão de produto concorrente """
    return CompetitorProductCreateScraping(
        competitor_id=str(uuid4()),
        monitored_product_id=str(uuid4()),
        product_url="https://example.com/item"
    )

def test_not_product_page_raises_bad_request(monkeypatch):
    """ Garante que páginas sem produto retornam erro 400 """
    _patch_common(monkeypatch)
    redis = DummyRedis()
    monkeypatch.setattr(module, "redis_client", redis, raising=False)
    monkeypatch.setattr("shared.utils.redis_client.get_redis_client", lambda: redis)

    html = "<html><body><p>sem produto</p></body></html>"
    async def fake_playwright(url: str):
        return html

    monkeypatch.setattr("market_scraper.services.services_scraper_common.fetch_html_playwright", fake_playwright)
    monkeypatch.setattr("market_scraper.services.services_scraper_common.parser.looks_like_product_page", lambda _html: False)

    called = {"parse": False}

    def fake_parse(*a, **k):
        called["parse"] = True
        return {}

    monkeypatch.setattr(
        "market_scraper.services.services_scraper_common.parser.parse_product_details",
        fake_parse
    )

    payload = _payload()

    import types, sys
    sys.modules.setdefault("infra", types.ModuleType("infra"))
    sys.modules.setdefault("infra.db", types.SimpleNamespace(Base=None))
    from market_alert.services.services_scraper_competitor import scrape_competitor_product

    with pytest.raises(HTTPException) as exc:
        scrape_competitor_product(
            db=Mock(spec=Session),
            url=payload.product_url,
            user_id=uuid4(),
            payload=payload
        )

    assert exc.value.status_code == 400
    assert called["parse"] is False
