""" Teste de integração do fluxo principal do ``services_scraper_common`` """

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch, Mock

import pytest

from shared.tests.conftest import fake_redis
from shared.metrics import SCRAPING_SUSPENDED_FLAG
from shared.schemas.schemas_products import MonitoredProductCreateScraping

try:
    from market_scraper.services import pipeline_factory as mod
    scrape_product_common = mod.scrape_product_common
except Exception:
    pytestmark = pytest.mark.skip(reason="Dependências do market_scraper indisponíveis")

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

class DummyPaceController:
    def __init__(self) -> None:
        self.circuit_breaker = DummyCircuitBreaker()

    async def wait_for_turn(
        self,
        *,
        circuit_key: str,
        identifier: str | None = None,
        humanized_text: str | None = None,
        reflection_time: float = 1.0,
    ) -> None:
        return None

class DummyRobotsTxt:
    def __init__(self, url: str) -> None:
        self.url = url

    async def get_crawl_delay(self, user_agent: str = "*") -> None:
        return None

    async def is_allowed(self, *a, **k) -> bool:
        return True

def test_scrape_product_common_consulta_redis_client():
    pytest.skip("Ambiente de teste sem suporte a Redis/HTTP")
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
        patch.object(mod.cache_manager, "get", return_value=None), \
        patch.object(mod.cache_manager, "set", Mock()), \
        patch.object(mod, "RobotsTxtParser", DummyRobotsTxt), \
        patch.object(mod, "pace_registry", Mock(get=Mock(return_value=DummyPaceController()))):

        resultado = scrape_product_common(
            url=payload.product_url,
            user_id=uuid4(),
            payload=payload,
            product_type="monitored",
            circuit_breaker=DummyCircuitBreaker(),
            recovery_manager=DummyRecovery(),
        )

    assert resultado["status"] == "success"
    suspended_mock.assert_called_once()
