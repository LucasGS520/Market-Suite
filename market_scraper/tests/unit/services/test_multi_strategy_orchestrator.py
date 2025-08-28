""" Testes para o ``MultiStrategyScraperOrchestrator`` """

from types import SimpleNamespace
from uuid import uuid4

import pytest

from market_scraper.services.multi_strategy_orchestrator import MultiStrategyScraperOrchestrator
from shared.metrics.metrics_scraper import SCRAPER_FALLBACK_TOTAL, SCRAPER_STRATEGY_TOTAL


class EstrategiaFalha:
    """ Estratégia que sempre lança exceção """
    def supports_url(self, url: str) -> bool:
        return True

    async def get_data(self, **k):
        raise RuntimeError("falha")

class EstrategiaSucesso:
    """ Estratégia que retorna dados válidos """
    def supports_url(self, url: str) -> bool:
        return True

    async def get_data(self, **k):
        return {
            "status": "success",
            "details": {"name": "Produto", "current_price": "10"},
        }

@pytest.mark.asyncio
async def test_contadores_de_fallback_e_estrategia():
    """ Deve registrar fallback e contadores das estratégias """
    #Reinicia contadores
    SCRAPER_STRATEGY_TOTAL._metrics.clear()
    SCRAPER_FALLBACK_TOTAL._value.set(0)

    orchestrator = MultiStrategyScraperOrchestrator(
        strategy_selector=lambda url: [EstrategiaFalha(), EstrategiaSucesso()]
    )

    resultado = await orchestrator.scrape(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=SimpleNamespace(),
        product_type="monitored",
    )

    assert resultado["status"] == "success"
    #A primeira estratégia falhou e a segunda teve sucesso
    assert (SCRAPER_STRATEGY_TOTAL.labels("EstrategiaFalha", "exception")._value.get() == 1)
    assert (SCRAPER_STRATEGY_TOTAL.labels("EstrategiaSucesso", "success")._value.get() == 1)

    #Houve um fallback entre as estratégias
    assert SCRAPER_FALLBACK_TOTAL._value.get() == 1
