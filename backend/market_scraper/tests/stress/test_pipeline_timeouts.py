from __future__ import annotations

import asyncio

import pytest

from market_scraper.services.synergic_pipeline import (
    PipelineContext,
    PipelineStep,
    PipelineTimeoutError,
    StepResult,
    SynergicPipeline,
)


class _SlowEmptyStep(PipelineStep):
    def __init__(self, *, name: str, delay_seconds: float, timeout: float | None = None) -> None:
        super().__init__(name=name, timeout=timeout)
        self._delay_seconds = delay_seconds

    async def run(self, context: PipelineContext) -> StepResult:
        await asyncio.sleep(self._delay_seconds)
        return StepResult.empty(message=f"{self.name}_completed")


class _SuccessPayloadStep(PipelineStep):
    def __init__(self, *, name: str, payload: dict[str, str]) -> None:
        super().__init__(name=name)
        self._payload = payload

    async def run(self, context: PipelineContext) -> StepResult:
        return StepResult.success(payload=self._payload, message=f"{self.name}_success")


async def test_step_timeout_limit_is_deterministic_and_pipeline_continues():
    context = PipelineContext(
        url="https://example.com/product/stress-timeout",
        source="example.com",
        default_step_timeout=0.01,
    )
    pipeline = SynergicPipeline(
        steps=[
            _SlowEmptyStep(name="slow_fetch", delay_seconds=0.03),
            _SuccessPayloadStep(
                name="fallback_parser",
                payload={
                    "name": "Stress Timeout",
                    "current_price": "10.00",
                },
            ),
        ],
        step_timeout=0.01,
        pipeline_timeout=0.2,
    )

    outcome = await pipeline.run(context)

    assert outcome.status == "success"
    assert outcome.payload is not None
    assert outcome.payload["name"] == "Stress Timeout"
    assert [step.name for step in outcome.steps] == ["slow_fetch", "fallback_parser"]
    assert [step.status for step in outcome.steps] == ["timeout", "success"]


async def test_global_pipeline_timeout_is_deterministic():
    context = PipelineContext(
        url="https://example.com/product/global-timeout",
        source="example.com",
        default_step_timeout=0.1,
    )
    pipeline = SynergicPipeline(
        steps=[
            _SlowEmptyStep(name="slow_fetch", delay_seconds=0.05, timeout=0.1),
            _SlowEmptyStep(name="slow_parser", delay_seconds=0.05, timeout=0.1),
        ],
        step_timeout=0.1,
        pipeline_timeout=0.01,
    )

    with pytest.raises(PipelineTimeoutError, match="Tempo limite do pipeline excedido"):
        await pipeline.run(context)
