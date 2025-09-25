from __future__ import annotations

from uuid import uuid4
from decimal import Decimal
from typing import Any

import pytest

from market_scraper.services.services_scraper_common import scrape_product_common_async
from shared.schemas.schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping
from market_scraper.services.synergic_pipeline import PipelineStep
from market_scraper.services.domain_policy import FeatureFlagDecision
from market_scraper.parsers.html_static import parse_meli_html


#HTML de exemplo representando uma página válida de produto no Mercado Livre
HTML_EXEMPLO = """
<html>
<head>
    <meta property="og:type" content="product" />
    <meta property="og:image" content="http://example.com/thumb.jpg" />
    <meta itemprop="priceCurrency" content="R$" /> 
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
    <span class="andes-money-amount__fraction">100</span>
    <span class="andes-money-amount__cents">00</span>
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

class DummyCircuitBreaker:
    def allow_request(self, key: str) -> bool:
        return True

    def record_failure(self, key: str) -> None:
        pass

    def record_success(self, key: str) -> None:
        pass

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

class PipelineCarregaHtml(PipelineStep):
    def __init__(self, html: str) -> None:
        self.html = html

    async def run(self, shared_context: dict[str, Any]) -> dict[str, Any]:
        shared_context["html"] = self.html
        return {"status": "success", "shared_context": {"html": self.html}}
    
class PipelineParserMeli(PipelineStep):
    def __init__(self, tracker: dict[str, Any]) -> None:
        self.tracker = tracker

    async def run(self, shared_context: dict[str, Any]) -> dict[str, Any]:
        html = shared_context.get("html", "")
        self.tracker["html"] = html
        self.tracker["url"] = shared_context.get("url")
        detalhes = parse_meli_html(html, shared_context.get("url", ""))
        return {
            "status": "success",
            "details": detalhes,
            "extraction_method": self.__class__.__name__,
        }

@pytest.fixture
def setup_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = FakeRedis()
    #Substitui todas as instâncias de Redis pelo mock em memória
    monkeypatch.setattr("shared.utils.redis_client.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("market_scraper.utils.robots_txt.get_redis_client", lambda: fake_redis)

    #Impedindo delays e leituras de robots.txt
    async def fake_fetch_robots(self, user_agent: str):
        return ""

    monkeypatch.setattr("market_scraper.utils.robots_txt.RobotsTxtParser._fetch_robots", fake_fetch_robots)

    async def fake_wait_async(self, text: str | None, reflection_time: float = 1.0) -> None:
        return None

    monkeypatch.setattr("market_scraper.utils.humanized_delay.HumanizedDelayManager.wait_async", fake_wait_async)

    async def fake_wait_for_turn(self, *, circuit_key: str, identifier: str | None = None, humanized_text: str | None = None, reflection_time: float = 1.0) -> None:
        return None

    monkeypatch.setattr("market_scraper.utils.pace_control.DomainPaceController.wait_for_turn", fake_wait_for_turn)
    monkeypatch.setattr("market_scraper.services.services_scraper_common.pace_registry", type("DummyRegistry", (), {"get": lambda self, host: DummyPaceController()})())

    def _fake_feature_flag(feature: str, url: str, *, context: str = "default", identifier: str | None = None, **kwargs) -> FeatureFlagDecision:
        return FeatureFlagDecision(
            feature=feature,
            context=context,
            enabled=True,
            config_enabled=True,
            rollout_percentage=100.0,
            source="tests",
            identifier=identifier,
            bucket_value=0.0,
            configured=True,
        )
    
    monkeypatch.setattr("market_scraper.services.services_scraper_common.evaluate_feature_flag", _fake_feature_flag)
    monkeypatch.setattr("market_scraper.services.services_scraper_common.pipeline_execution_mode_for", lambda *a, **k: "sequential")

@pytest.mark.asyncio
async def test_scrape_monitored_product_flow(setup_ambiente: None, monkeypatch: pytest.MonkeyPatch) -> None:
    rastreador: dict[str, Any] = {}

    def _fake_pipeline_steps(url: str, *, context: str = "default") -> list[PipelineStep]:
        return [PipelineCarregaHtml(HTML_EXEMPLO), PipelineParserMeli(rastreador)]
    
    monkeypatch.setattr("market_scraper.services.services_scraper_common.pipeline_steps_for", _fake_pipeline_steps)

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
        circuit_breaker=DummyCircuitBreaker(),
    )
    detalhes = resultado["details"]
    
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Exemplo"
    assert detalhes["current_price"] == "R$ 100,00"
    assert rastreador["html"].strip().startswith("<html>")
    assert rastreador["url"] == str(payload.product_url)

@pytest.mark.asyncio
async def test_scrape_competitor_product_flow(setup_ambiente: None, monkeypatch: pytest.MonkeyPatch) -> None:
    rastreador: dict[str, Any] = {}

    def _fake_pipeline_steps(url: str, *, context: str = "default") -> list[PipelineStep]:
        return [PipelineCarregaHtml(HTML_EXEMPLO), PipelineParserMeli(rastreador)]
    
    monkeypatch.setattr("market_scraper.services.services_scraper_common.pipeline_steps_for", _fake_pipeline_steps)

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
        circuit_breaker=DummyCircuitBreaker(),
    )
    detalhes = resultado["details"]
    assert resultado["status"] == "success"
    assert detalhes["name"] == "Produto Exemplo"
    assert detalhes["current_price"] == "R$ 100,00"
    assert rastreador["url"] == str(payload.product_url)
