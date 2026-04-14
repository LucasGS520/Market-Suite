from __future__ import annotations

import asyncio

from market_scraper.services.pipeline_factory import build_context
from market_scraper.services.synergic_pipeline import (
    PipelineContext,
    PipelineStep,
    StepResult,
    SynergicPipeline,
)


class _StaticStep(PipelineStep):
    def __init__(self, result: StepResult, *, name: str) -> None:
        super().__init__(name=name)
        self._result = result

    async def run(self, context: PipelineContext) -> StepResult:
        return self._result


def test_pipeline_context_initializes_trace_data_and_cache_bypass():
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=2.0,
        force_refresh=True,
    )

    assert context.trace_id is not None
    assert context.data["url"] == "https://example.com/product"
    assert context.data["source"] == "example.com"
    assert context.data["domain"] == "example.com"
    assert context.data["step_timeout"] == 2.0
    assert context.data["force_refresh"] is True
    assert context.should_use_cache("html") is False
    assert context.data["cache_bypass"] == ["html"]


def test_pipeline_context_build_payload_keeps_defaults_and_extra_fields():
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )

    payload = context.build_payload(
        {
            "name": "Produto",
            "current_price": "12.34",
            "sku": "ABC-123",
        }
    )

    assert payload["url"] == "https://example.com/product"
    assert payload["source"] == "example.com"
    assert payload["name"] == "Produto"
    assert payload["current_price"] == "12.34"
    assert payload["sku"] == "ABC-123"
    assert payload["availability"] is None


def test_build_context_extracts_source_and_force_refresh_flag():
    context = build_context(
        "https://shop.example.com/item/1",
        step_timeout=3.0,
        force_refresh=True,
        trace_id="trace-1",
    )

    assert context.source == "shop.example.com"
    assert context.default_step_timeout == 3.0
    assert context.force_refresh is True
    assert context.trace_id == "trace-1"


def test_synergic_pipeline_returns_success_when_step_emits_payload():
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )
    pipeline = SynergicPipeline(
        steps=[
            _StaticStep(StepResult.empty("no-data"), name="fetch"),
            _StaticStep(
                StepResult.success(
                    payload={"name": "Produto", "current_price": "10.00"}
                ),
                name="parser",
            ),
        ],
        step_timeout=1.0,
        pipeline_timeout=3.0,
    )

    outcome = asyncio.run(pipeline.run(context))

    assert outcome.status == "success"
    assert outcome.payload is not None
    assert outcome.payload["url"] == "https://example.com/product"
    assert [step.status for step in outcome.steps] == ["empty", "success"]
