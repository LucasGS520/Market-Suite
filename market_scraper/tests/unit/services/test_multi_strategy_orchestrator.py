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

class EstrategiaDadosInvalidos:
    """ Estratégia qye retorna campos vazios, considerados inválidos """
    def supports_url(self, url: str) -> bool:
        return True

    async def get_data(self, **k):
        return {
            "status": "success",
            "details": {"name": "", "current_price": ""},
        }

class EstrategiaSucesso:
    """ Estratégia que retorna dados válidos """
    def supports_url(self, url: str) -> bool:
        return True

    async def get_data(self, **k):
        return {
            "status": "success",
            "details": {"name": "Produto", "current_price": "10"},
        }

class EstrategiaLenta:
    """ Estrategia que demora para responder """
    def supports_url(self, url: str) -> bool:
        return True

    async def get_data(self, **k):
        import asyncio
        await asyncio.sleep(0.1)
        return {"status": "success"}

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

@pytest.mark.asyncio
async def test_fallback_quando_timeout():
    """ Deve acionar fallback quando a primeira estratégia excede o tempo limite """
    SCRAPER_STRATEGY_TOTAL._metrics.clear()
    SCRAPER_FALLBACK_TOTAL._value.set(0)

    orchestrator = MultiStrategyScraperOrchestrator(
        strategy_selector=lambda url: [EstrategiaLenta(), EstrategiaSucesso()],
        strategy_timeout=0.01,
    )

    resultado = await orchestrator.scrape(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=SimpleNamespace(),
        product_type="monitored",
    )

    assert resultado["status"] == "success"
    assert (
        SCRAPER_STRATEGY_TOTAL.labels("EstrategiaLenta", "timeout")._value.get() == 1
    )
    assert (
        SCRAPER_STRATEGY_TOTAL.labels("EstrategiaSucesso", "success")._value.get() == 1
    )
    assert SCRAPER_FALLBACK_TOTAL._value.get() == 1

@pytest.mark.asyncio
async def test_fallback_quando_dados_invalidos():
    """ Deve acionar fallback quando a primeira estratégia retorna dados inválidos """
    #Reinicia contadores para cenário de teste
    SCRAPER_STRATEGY_TOTAL._metrics.clear()
    SCRAPER_FALLBACK_TOTAL._value.set(0)

    orchestrator = MultiStrategyScraperOrchestrator(
        strategy_selector=lambda url: [EstrategiaDadosInvalidos(), EstrategiaSucesso()]
    )

    resultado = await orchestrator.scrape(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=SimpleNamespace(),
        product_type="monitored",
    )

    #O retorno final deve vir da segunda estratégia com dados válidos
    assert resultado["status"] == "success"
    assert resultado["details"]["name"] == "Produto"
    assert resultado["details"]["current_price"] == "10"

    #A primeira estratégia forneceu dados inválidos e a segunda obteve sucesso
    assert (
        SCRAPER_STRATEGY_TOTAL.labels("EstrategiaDadosInvalidos", "invalid")._value.get() == 1
    )
    assert (
        SCRAPER_STRATEGY_TOTAL.labels("EstrategiaSucesso", "success")._value.get() == 1
    )

    #O orchestrador acionou fallback entre as duas estratégias
    assert SCRAPER_FALLBACK_TOTAL._value.get() == 1
