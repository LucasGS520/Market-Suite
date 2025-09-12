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

class EstrategiaDefineContexto:
    """ Estratégia que apenas define valor no contexto """
    def supports_url(self, url: str) -> bool:
        return True
    
    async def get_data(self, **k):
        ctx = k.get("shared_context")
        ctx["token"] = "xyz"
        return {"status": "error", "shared_context": ctx}
    
class EstrategiaUsaContexto:
    """ Estratégia que lê valor previamente definido """
    def supports_url(self, url: str) -> bool:
        return True
    
    async def get_data(self, **k):
        ctx = k.get("shared_context")
        # Corrige para retornar sucesso e usar o valor do contexto
        return {
            "status": "success",
            "details": {"name": ctx.get("token", ""), "current_price": "1"}
        }

class EstrategiaErroSimples:
    """ Estratégia que apenas retorna erro """
    def supports_url(self, url: str) -> bool:
        return True
    
    async def get_data(self, **k):
        return {"status": "error"}
    
class EstrategiaRaquerLogin:
    """ Estratégia que depende da etapa de Login """
    dependencies = {"login"}

    def supports_url(self, url: str) -> bool:
        return True
    
    async def get_data(self, **k):
        ctx = k.get("shared_context", {})
        return {
            "status": "success",
            "details": {"name": ctx.get("usuario", ""), "current_price": "1"},
        }
    
async def resolver_login(**k):
    """" Simula etapa de login e atualiza o contexto compartilhado """
    ctx = k.get("shared_context")
    ctx["login"] = True
    ctx["usuario"] = "logado"
    return ctx

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
async def test_resolucao_de_dependencias():
    """ Deve resolver dependências declaradas antes da execução """
    SCRAPER_STRATEGY_TOTAL._metrics.clear()
    SCRAPER_FALLBACK_TOTAL._value.set(0)

    orchestrator = MultiStrategyScraperOrchestrator(
        strategy_selector=lambda url: [],
        dependency_resolvers={"login": resolver_login},
    )

    resultado = await orchestrator.scrape(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=SimpleNamespace(),
        product_type="monitored",
        strategies=[EstrategiaRaquerLogin()],
        shared_context={},
    )

    assert resultado["status"] == "success"
    assert resultado["details"]["name"] == "logado"
    assert SCRAPER_FALLBACK_TOTAL._value.get() == 0

@pytest.mark.asyncio
async def test_fallback_quando_dependencia_ausente():
    """ Deve pular estratégia sem resolver dependência e acionar fallback """
    SCRAPER_STRATEGY_TOTAL._metrics.clear()
    SCRAPER_FALLBACK_TOTAL._value.set(0)

    orchestrator = MultiStrategyScraperOrchestrator(
        strategy_selector=lambda url: [],
    )

    resultado = await orchestrator.scrape(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=SimpleNamespace(),
        product_type="monitored",
        strategies=[EstrategiaRaquerLogin(), EstrategiaSucesso()],
        shared_context={},
    )

    assert resultado["status"] == "success"
    assert resultado["details"]["name"] == "Produto"
    #Fallback foi acionado pois a primeira estratégia foi pulada
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

@pytest.mark.asyncio
async def test_compartilhamento_de_contexto():
    """ Deve compartilhar dados entre estratégias sequenciais """
    SCRAPER_STRATEGY_TOTAL._metrics.clear()
    SCRAPER_FALLBACK_TOTAL._value.set(0)

    orchestrator = MultiStrategyScraperOrchestrator(
        strategy_selector=lambda url: [],
    )

    resultado = await orchestrator.scrape(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=SimpleNamespace(),
        product_type="monitored",
        strategies=[EstrategiaDefineContexto(), EstrategiaUsaContexto()],
        shared_context={},
    )

    assert resultado["status"] == "success"
    assert resultado["details"]["name"] == "xyz"
    #Houve fallback pois a primeira estratégia não retornou sucesso
    assert SCRAPER_FALLBACK_TOTAL._value.get() == 1

@pytest.mark.asyncio
async def test_execucao_em_paralelo():
    """ Deve executar estratégias em paralelo e retornar o primeiro sucesso """
    SCRAPER_STRATEGY_TOTAL._metrics.clear()
    SCRAPER_FALLBACK_TOTAL._value.set(0)

    orchestrator = MultiStrategyScraperOrchestrator(
        strategy_selector=lambda url: [],
    )

    resultado = await orchestrator.scrape(
        url="https://exemplo.com/item",
        user_id=uuid4(),
        payload=SimpleNamespace(),
        product_type="monitored",
        strategies=[EstrategiaErroSimples(), EstrategiaSucesso()],
        execution_mode="parallel",
    )

    assert resultado["status"] == "success"
    assert (
        SCRAPER_STRATEGY_TOTAL.labels("EstrategiaErroSimples", "error")._value.get() == 1
    )
    assert (
        SCRAPER_STRATEGY_TOTAL.labels("EstrategiaSucesso", "success")._value.get() == 1
    )
    assert SCRAPER_FALLBACK_TOTAL._value.get() == 1
