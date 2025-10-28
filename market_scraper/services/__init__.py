""" Facilita acesso às principais funções e classes do serviço """

from .pipeline_factory import build_context, create_pipeline, run_pipeline
from .pipeline_steps import (
    FetchHTMLStep,
    GenericFallbackParserStep,
    HtmlMetadataParserStep,
    JsonLdParserStep,
    default_pipeline_steps,
)
from .synergic_pipeline import (
    PipelineContext,
    PipelineOutcome,
    PipelineTimeoutError,
    SynergicPipeline,
    StepExecution,
    StepResult,
)


__all__ = [
    "build_context",
    "create_pipeline",
    "run_pipeline",
    "FetchHTMLStep",
    "GenericFallbackParserStep",
    "HtmlMetadataParserStep",
    "JsonLdParserStep",
    "default_pipeline_steps",
    "PipelineContext",
    "PipelineOutcome",
    "PipelineTimeoutError",
    "SynergicPipeline",
    "StepExecution",
    "StepResult",
]
