from __future__ import annotations

from uuid import uuid4
from decimal import Decimal

import pytest

from market_scraper.services.services_scraper_common import scrape_product_common_async
from market_scraper.tests.unit.conftest import fake_redis
from shared.schemas.schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping
from market_scraper.strategies.html_static import MercadoLivreHtmlStaticStrategy


#HTML de exemplo representando uma página válida de produto no Mercado Livre
HTML_EXEMPLO = """
<html>
<head>
    <meta property="og:type" content="product" />
    <meta property="og:image" content="http://example.com/thumb.jpg" />
    <script type="application/ld+json">
    {
        "@type": "Product",
        "name": "Produto Exemplo",
        "offers": {"price": "100.00", "priceBeforeDiscount": "150.00"},
        "seller": {"name": "Loja Teste"}
    }
    </script>
</head>
<body>
    <h1 class="ui-pdp-title">Produto Exemplo</h1>
    <span>Frete grátis</span>
</body>
</html>
"""

class FakeRedis:
    def __init__(self) -> None:
        self._storage: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._storage.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self._storage[key] = value

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._storage[key] = value

    def exists(self, key: str) -> int:
        return 1 if key in self._storage else 0

    def delete(self, key: str) -> None:
        self._storage.pop(key, None)

class DummyRateLimiter:
    def allow_request(self, identifier: str | None = None) -> bool:
        return True

class DummyCircuitBreaker:
    def allow_request(self, key: str) -> bool:
        return True

    def record_failure(self, key: str) -> None:
        pass

    def record_success(self, key: str) -> None:
        pass

@pytest.fixture
def setup_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = FakeRedis()
    #Substitui todas as instâncias de Redis pelo mock em memória
    monkeypatch.setattr("shared.utils.redis_client.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("market_scraper.utils.robots_txt.get_redis_client", lambda: fake_redis)

    #Impedindo delays e leituras de robots.txt
    async def fake_fetch_robots(self):
        return ""

    monkeypatch.setattr("market_scraper.utils.robots_txt.RobotsTxtParser._fetch_robots", fake_fetch_robots)

    async def fake_wait_async(self, text: str | None, reflection_time: float = 1.0) -> None:
        return None

    monkeypatch.setattr("market_scraper.utils.humanized_delay.HumanizedDelayManager.wait_async", fake_wait_async)

    def fake_throttle_wait(self, circuit_key: str, identifier: str | None = None) -> None:
        return None

    async def fake_throttle_wait_async(self, circuit_key: str, identifier: str | None = None) -> None:
        return None

    monkeypatch.setattr("market_scraper.utils.throttle_manager.ThrottleManager.wait", fake_throttle_wait)
    monkeypatch.setattr("market_scraper.utils.throttle_manager.ThrottleManager.wait_async", fake_throttle_wait_async)

    async def fake_fetch_html_static(self, url: str) -> str:
        return HTML_EXEMPLO

    monkeypatch.setattr(MercadoLivreHtmlStaticStrategy, "_fetch_html", fake_fetch_html_static)

@pytest.mark.asyncio
async def test_scrape_monitored_product_flow(setup_ambiente: None) -> None:
    user_id = uuid4()
    payload = MonitoredProductCreateScraping(
        name_identification="Produto X",
        product_url="https://www.mercadolivre.com.br/p/abc",
        target_price=Decimal("200.00"),
    )
    resultado = await scrape_product_common_async(
        url=str(payload.product_url),
        user_id=user_id,
        payload=payload,
        product_type="monitored",
        rate_limiter=DummyRateLimiter(),
        circuit_breaker=DummyCircuitBreaker(),
    )
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Exemplo"
    assert detalhes["current_price"] == "R$ 100,00"

@pytest.mark.asyncio
async def test_scrape_competitor_product_flow(setup_ambiente: None) -> None:
    user_id = uuid4()
    payload = CompetitorProductCreateScraping(
        monitored_product_id=uuid4(),
        product_url="https://www.mercadolivre.com.br/p/xyz",
    )
    resultado = await scrape_product_common_async(
        url=str(payload.product_url),
        user_id=user_id,
        payload=payload,
        product_type="competitor",
        rate_limiter=DummyRateLimiter(),
        circuit_breaker=DummyCircuitBreaker(),
    )
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Exemplo"
    assert detalhes["current_price"] == "R$ 100,00"
