""" Testes do factory de pipeline do serviço de scraping """

from __future__ import annotations

import pytest

from market_scraper.services.pipeline_factory import build_context, create_pipeline, run_pipeline
from market_scraper.services.synergic_pipeline import PipelineOutcome, SynergicPipeline


@pytest.mark.asyncio
async def test_run_pipeline_usa_contexto_e_pipeline_injetado(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante que o factory injeta contexto e chama o pipeline esperado """
    capturado: dict[str, object] = {}

    class _PipelineStub:
        """Pipeline simples para capturar o contexto gerado."""
        async def run(self, context):
            #Registramos o contexto para validar os parâmetros recebidos
            capturado["contexto"] = context
            return PipelineOutcome(status="no_result", context=context)

    def _pipeline_factory_stub(**_kwargs):
        return _PipelineStub()

    monkeypatch.setattr(
        "market_scraper.services.pipeline_factory.create_pipeline",
        _pipeline_factory_stub,
    )

    resultado = await run_pipeline(
        "https://exemplo.com/produto",
        force_refresh=True,
        trace_id="trace-teste",
    )

    assert resultado.status == "no_result"
    contexto = capturado["contexto"]
    assert contexto.url == "https://exemplo.com/produto"
    assert contexto.force_refresh is True
    assert contexto.trace_id == "trace-teste"


def test_build_context_normaliza_origem() -> None:
    """ Confirma que o contexto usa o hostname como fonte padrão """
    contexto = build_context("https://exemplo.com/produto")

    assert contexto.source == "exemplo.com"


def test_create_pipeline_retornar_instancia() -> None:
    """ Verifica que o factory cria uma instância do pipeline """
    pipeline = create_pipeline()

    assert isinstance(pipeline, SynergicPipeline)
    