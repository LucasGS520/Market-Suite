from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from market_scraper.services.synergic_pipeline import (
    PipelineContext,
    PipelineStep,
    PipelineTimeoutError,
    StepResult,
    SynergicPipeline,
)

@dataclass
class DummyStep(PipelineStep):
    """ Etapa simulada para facilitar os cenários de teste """
    result: StepResult
    delay: float = 0.0

    def __post_init__(self) -> None:
        super().__init__(name="dummy")

    async def run(self, context: PipelineContext) -> StepResult:
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.result
    
class ErrorStep(PipelineStep):
    """ Etapa que sempre lança erro para validar cenários de falha """

    def __init__(self) -> None:
        super().__init__(name="error_step")

    async def run(self, context: PipelineContext) -> StepResult:
        raise RuntimeError("falha controlada")

@pytest.mark.asyncio
async def test_pipeline_returns_first_success() -> None:
    """ Confirma que o pipeline encerra ao encontrar o primeiro sucesso """
    context = PipelineContext(url="https://exemplo.com", source="exemplo.com", default_step_timeout=0.5)
    steps = [
        DummyStep(StepResult.empty("sem dados")),
        DummyStep(StepResult.success({"name": "Produto", "current_price": "10.00"})),
        DummyStep(StepResult.success({"name": "Outro", "current_price": "20.00"})),
    ]
    pipeline = SynergicPipeline(steps=steps, step_timeout=0.5, pipeline_timeout=1.0)
    outcome = await pipeline.run(context)
    assert outcome.status == "success"
    assert outcome.payload == {
        "name": "Produto",
        "current_price": "10.00",
        "url": "https://exemplo.com",
        "source": "exemplo.com",
        "currency": None,
        "availability": None,
        "last_status": None,
        "payload": None,
    }
    assert len(outcome.steps) == 2
    assert outcome.context is context

@pytest.mark.asyncio
async def test_pipeline_records_timeout(monkeypatch) -> None:
    """ Verifica que o timeout de etapa registra fallback e continua """
    context = PipelineContext(url="https://exemplo.com", source="exemplo.com", default_step_timeout=0.1)
    slow_step = DummyStep(StepResult.success({"name": "Lento", "current_price": "30.00"}), delay=0.3)
    fast_step = DummyStep(StepResult.success({"name": "Rápido", "current_price": "40.00"}))
    pipeline = SynergicPipeline(steps=[slow_step, fast_step], step_timeout=0.1, pipeline_timeout=1.0)
    outcome = await pipeline.run(context)
    assert outcome.status == "success"
    assert outcome.payload["name"] == "Rápido"
    assert any(record.status == "timeout" for record in outcome.steps)

@pytest.mark.asyncio
async def test_pipeline_global_timeout() -> None:
    """ Garante que o timeout global dispara ``PipelineTimeoutError`` """
    context = PipelineContext(url="https://exemplo.com", source="exemplo.com", default_step_timeout=0.5)
    step = DummyStep(StepResult.success({"name": "Produto", "current_price": "10.00"}), delay=1.0)
    pipeline = SynergicPipeline(steps=[step], step_timeout=1.0, pipeline_timeout=0.2)
    with pytest.raises(PipelineTimeoutError):
        await pipeline.run(context)

@pytest.mark.asyncio
async def test_pipeline_context_initializes_shared_keys() -> None:
    """ Verifica que o contexto compartilha metadados mínimos automaticamente """
    context = PipelineContext(url="https://exemplo.com", source="exemplo.com", default_step_timeout=0.5)
    step = DummyStep(StepResult.empty("sem dados"))
    pipeline = SynergicPipeline(steps=[step], step_timeout=0.5, pipeline_timeout=1.5)

    outcome = await pipeline.run(context)

    assert outcome.status == "no_result"
    assert context.data["url"] == context.url
    assert context.data["source"] == context.source
    assert context.data["domain"] == context.source
    assert context.data["step_timeout"] == context.default_step_timeout
    assert context.data["pipeline_timeout"] == pytest.approx(1.5)
    
@pytest.mark.asyncio
async def test_pipeline_propagates_error_status() -> None:
    """ Confirma que erros de etapa são refletidos no ``PipelineOutcome`` """

    context = PipelineContext(url="https://exemplo.com", source="exemplo.com", default_step_timeout=0.5)
    pipeline = SynergicPipeline(steps=[ErrorStep()], step_timeout=0.5, pipeline_timeout=1.0)

    outcome = await pipeline.run(context)

    assert outcome.status == "error"
    assert outcome.payload is None
    assert any(record.status == "error" for record in outcome.steps)


@pytest.mark.asyncio
async def test_pipeline_propagates_timeout_status() -> None:
    """ Garante que timeouts de etapa definem status final consistente """

    context = PipelineContext(url="https://exemplo.com", source="exemplo.com", default_step_timeout=0.05)
    slow_step = DummyStep(StepResult.success({"name": "Lento", "current_price": "10.00"}), delay=0.2)
    pipeline = SynergicPipeline(steps=[slow_step], step_timeout=0.05, pipeline_timeout=1.0)

    outcome = await pipeline.run(context)

    assert outcome.status == "timeout"
    assert outcome.payload is None
    assert any(record.status == "timeout" for record in outcome.steps)
