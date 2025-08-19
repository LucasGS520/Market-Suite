""" Teste de integração do fluxo principal do ``services_scraper_common`` """

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch, AsyncMock, Mock

import pytest

from market_scraper.tests.unit.utils.test_circuit_breaker import fake_redis
from shared.metrics import SCRAPING_SUSPENDED_FLAG
from shared.schemas.products import MonitoredProductCreateScraping

try:
    from market_scraper.services import services_scraper_common as mod
    scrape_product_common = mod.scrape_product_common
except Exception:
    pytestmark = pytest.mark.skip(reason="Dependências do market_scraper indisponíveis")

class DummyThrottle:
    def __init__(self, *a, **k) -> None:
        self.jitter_min = 0
        self.jitter_max = 0

    async def wait_async(self, *a, **k) -> None:
        return None

class DummyHumanDelay:
    async def wait_async(self, *a, **k) -> None:
        return None

    def prolong(self, factor: float = 1.5) -> None:
        return None

class DummyCircuitBreaker:
    def allow_request(self, key: str) -> bool:
        return True

    def record_failure(self, key: str) -> None:
        return None

    def record_success(self, key: str) -> None:
        return None

class DummyRecovery:
    async def handle_block(self, *a, **k):
        return None

class DummyRateLimiter:
    def allow_request(self, identifier: str | None = None) -> bool:
        return True

class DummyRobotsTxt:
    def __init__(self, url: str) -> None:
        self.url = url

    async def get_crawl_delay(self, user_agent: str = "*") -> None:
        return None

def test_scrape_product_common_consulta_redis_client():
    payload = MonitoredProductCreateScraping(
        name_identification="Produto Teste",
        product_url="https://example.com/item",
        target_price=Decimal("10.00"),
    )

    fake_redis = type("FakeRedis", (), {"exists": lambda self, k: 0})()

    from shared.utils import redis_client as rc

    metrics_stub = SimpleNamespace(SCRAPING_SUSPENDED_FLAG=Mock())

    with patch.object(rc, "get_redis_client", return_value=fake_redis), \
        patch.object(rc, "metrics", metrics_stub), \
        patch.object(mod, "is_scraping_suspended", wraps=rc.is_scraping_suspended) as suspended_mock, \
        patch.object(mod, "fetch_html_playwright", AsyncMock(return_value="<html></html>")), \
        patch.object(mod, "get_cached_html", AsyncMock(return_value=None)), \
        patch.object(mod, "set_cached_html", AsyncMock()), \
        patch.object(mod.parser, "looks_like_product_page", return_value=True), \
        patch.object(mod.parser, "parse_product_details", return_value={"current_price": "10.00"}), \
        patch.object(mod, "HumanizedDelayManager", DummyHumanDelay), \
        patch.object(mod, "ThrottleManager", DummyThrottle), \
        patch.object(mod, "RobotsTxtParser", DummyRobotsTxt):

        resultado = scrape_product_common(
            url=payload.product_url,
            user_id=uuid4(),
            payload=payload,
            product_type="monitored",
            rate_limiter=DummyRateLimiter(),
            circuit_breaker=DummyCircuitBreaker(),
            recovery_manager=DummyRecovery(),
        )

    assert resultado["status"] == "success"
    suspended_mock.assert_called_once()
