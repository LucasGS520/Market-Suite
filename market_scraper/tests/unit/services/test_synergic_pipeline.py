""" Teste para o ``SynergicPipeline`` """

import pytest

from market_scraper.services.synergic_pipeline import PipelineStep, SynergicPipeline


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
    