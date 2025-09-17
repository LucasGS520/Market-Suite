""" Teste para o ``SynergicPipeline`` """

import pytest

from market_scraper.services.synergic_pipeline import PipelineStep, SynergicPipeline


class ContadorSimples:
    """ Estrutura mínima para registrar incrementos de métricas """
    def __init__(self) -> None:
        self.total = 0
        self.rotulos: list[tuple] = []

    def labels(self, *rotulos: str):
        """ Guarda os rótulos utilizados antes de incrementar """
        self.rotulos.append(rotulos)
        return self
    
    def inc(self, valor: int = 1) -> None:
        """ Soma o valor informado ao total acumulado """
        self.total += valor

class HistogramSimples(ContadorSimples):
    """ Versão simplificada para observar valores de latência """
    def __init__(self) -> None:
        super().__init__()
        self.observacoes: list[float] = []

    def observe(self, valor: float) -> None:
        """ Registra o valor observado mantendo compatibilidade  """
        self.observacoes.append(valor)

class EtapaDefineContexto(PipelineStep):
    """ Etapa que insere valor no ``shared_context`` """
    async def run(self, shared_context):
        shared_context["token"] = "abc"
        return {"status": "ok", "shared_context": {"token": "abc"}}
    
class EtapaUsaContexto(PipelineStep):
    """ Etapa que consome valor previamente definido """
    async def run(self, shared_context):
        return {"status": "ok", "valor": shared_context.get("token")}
    
class EtapaCondicional(PipelineStep):
    """ Executa apenas se chave ``executar`` estiver presente """
    def should_run(self, shared_context):
        return shared_context.get("executar", False)
    
    async def run(self, shared_context):
        shared_context["executou"] = True
        return {"status": "ok", "shared_context": {"executou": True}}
    
@pytest.mark.asyncio
async def test_pipeline_compartilha_contexto():
    """ Deve propagar dados entre etapas sequenciais """
    pipeline = SynergicPipeline([EtapaDefineContexto(), EtapaUsaContexto()])
    resultado = await pipeline.run(shared_context={})

    assert resultado["results"][1]["valor"] == "abc"
    assert resultado["shared_context"]["token"] == "abc"

@pytest.mark.asyncio
async def test_pipeline_condicional():
    """ Deve executar etapa apenas qaundo condição for verdadeira """
    pipeline = SynergicPipeline(
        [EtapaCondicional()], execution_mode="conditional"
    )
    res1 = await pipeline.run(shared_context={})
    assert res1["results"] == []

    res2 = await pipeline.run(shared_context={"executar": True})
    assert res2["results"] != []
    assert res2["shared_context"]["executou"] is True
    
@pytest.mark.asyncio
async def test_pipeline_paralelo_registra_fallback(monkeypatch):
    """ Em modo paralelo deve registrar fallback para etapas com erro """
    class EtapaSucesso(PipelineStep):
        async def run(self, shared_context):
            return {"status": "success", "shared_context": {"ok": True}}
        
    class EtapaErro(PipelineStep):
        async def run(self, shared_context):
            raise RuntimeError("falha intencional")
        
    contador_fallback = ContadorSimples()
    contador_estrategia = ContadorSimples()
    histograma = HistogramSimples()

    monkeypatch.setattr("market_scraper.services.synergic_pipeline.SCRAPER_FALLBACK_TOTAL", contador_fallback)
    monkeypatch.setattr("market_scraper.services.synergic_pipeline.SCRAPER_STRATEGY_TOTAL", contador_estrategia)
    monkeypatch.setattr("market_scraper.services.synergic_pipeline.SCRAPING_LATENCY_SECONDS", histograma)

    pipeline = SynergicPipeline([EtapaSucesso(), EtapaErro()], execution_mode="parallel")
    resultado = await pipeline.run(shared_context={})

    assert len(resultado["results"]) == 2
    assert contador_fallback.total == 1
    assert contador_estrategia.total == 2
    assert len(histograma.observacoes) == 2

@pytest.mark.asyncio
async def test_pipeline_sequencial_fallback_intermediario(monkeypatch):
    """ Deve registrar fallback apenas para etapas anteriores ao sucesso """
    class EtapaFalha(PipelineStep):
        async def run(self, shared_context):
            return {"status": "error"}
        
    class EtapaSucesso(PipelineStep):
        async def run(self, shared_context):
            return {"status": "success"}
        
    contador_fallback = ContadorSimples()
    contador_estrategia = ContadorSimples()
    histograma = HistogramSimples()

    monkeypatch.setattr("market_scraper.services.synergic_pipeline.SCRAPER_FALLBACK_TOTAL", contador_fallback)
    monkeypatch.setattr("market_scraper.services.synergic_pipeline.SCRAPER_STRATEGY_TOTAL", contador_estrategia)
    monkeypatch.setattr("market_scraper.services.synergic_pipeline.SCRAPING_LATENCY_SECONDS", histograma)

    pipeline = SynergicPipeline([EtapaFalha(), EtapaSucesso()])
    resultado = await pipeline.run(shared_context={})

    assert resultado["status"] == "success"
    assert contador_fallback.total == 1
    assert contador_estrategia.total == 2
    assert len(histograma.observacoes) == 2
