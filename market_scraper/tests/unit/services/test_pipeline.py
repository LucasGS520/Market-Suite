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
    
@pytest.mark.asyncio
async def test_pipeline_returns_first_success() -> None:
    """ Confirma que o pipeline encerra ao encontrar o primeiro sucesso """
    context = PipelineContext(url="https://exemplo.com", source="exemplo.com", default_step_timeout=0.5)
    steps = [
        DummyStep(StepResult.empty("sem dados")),
        DummyStep(StepResult.success({"name": "Produto", "current_price": "10"})),
        DummyStep(StepResult.success({"name": "Outro", "current_price": "20"})),
    ]
    pipeline = SynergicPipeline(steps=steps, step_timeout=0.5, pipeline_timeout=1.0)
    outcome = await pipeline.run(context)
    assert outcome.status == "success"
    assert outcome.payload == {
        "name": "Produto",
        "current_price": "10",
        "url": "https://exemplo.com",
        "source": "exemplo.com",
    }
    assert len(outcome.steps) == 2

@pytest.mark.asyncio
async def test_pipeline_records_timeout(monkeypatch) -> None:
    """ Verifica que o timeout de etapa registra fallback e continua """
    context = PipelineContext(url="https://exemplo.com", source="exemplo.com", default_step_timeout=0.1)
    slow_step = DummyStep(StepResult.success({"name": "Lento", "current_price": "30"}), delay=0.3)
    fast_step = DummyStep(StepResult.success({"name": "Rápido", "current_price": "40"}))
    pipeline = SynergicPipeline(steps=[slow_step, fast_step], step_timeout=0.1, pipeline_timeout=1.0)
    outcome = await pipeline.run(context)
    assert outcome.status == "success"
    assert outcome.payload["name"] == "Rápido"
    assert any(record.status == "timeout" for record in outcome.steps)

@pytest.mark.asyncio
async def test_pipeline_global_timeout() -> None:
    """ Garante que o timeout global dispara ``PipelineTimeoutError`` """
    context = PipelineContext(url="https://exemplo.com", source="exemplo.com", default_step_timeout=0.5)
    step = DummyStep(StepResult.success({"name": "Produto", "current_price": "10"}), delay=1.0)
    pipeline = SynergicPipeline(steps=[step], step_timeout=1.0, pipeline_timeout=0.2)
    with pytest.raises(PipelineTimeoutError):
        await pipeline.run(context)
        