""" Funções auxiliares para montar e executar o pipeline enxuto

O módulo expõe um único ponto de criação do pipeline, encapsulando
as etapas padrão, timeouts e registro de métricas. Assim, a rota
``/scraper/parse`` pode focar apenas na validação da requisição.
"""

from __future__ import annotations

from urllib.parse import urlparse
from typing import Optional

import structlog

from shared.utils.logging_utils import sanitize_log_data

from market_scraper.core.config_scraper import settings
from market_scraper.services.pipeline_steps import default_pipeline_steps
from market_scraper.services.synergic_pipeline import (
    PipelineContext,
    PipelineOutcome,
    PipelineTimeoutError,
    SynergicPipeline,
)


logger = structlog.get_logger("services_scraper_common")

def _build_context(url: str, step_timeout: float) -> PipelineContext:
    """ Cria o contexto compartilhado a partir da URL normalizada """
    parsed = urlparse(url)
    source = parsed.hostname or parsed.netloc or "unknown"
    return PipelineContext(
        url=url,
        source=source,
        default_step_timeout=step_timeout,
    )

def create_pipeline(
    *,
    step_timeout: Optional[float] = None,
    pipeline_timeout: Optional[float] = None,
) -> SynergicPipeline:
    """ Instancia o ``SyergicPipeline`` com as etapas padrão """
    timeout_step = step_timeout or settings.SCRAPER_STEP_TIMEOUT_SECONDS
    timeout_pipeline = pipeline_timeout or settings.SCRAPER_PIPELINE_TIMEOUT_SECONDS
    return SynergicPipeline(
        steps=default_pipeline_steps(),
        step_timeout=timeout_step,
        pipeline_timeout=timeout_pipeline,
    )

def build_context(url: str, *, step_timeout: Optional[float] = None) -> PipelineContext:
    """ Encapsula a criação do contexto para facilitar testes """
    timeout_step = step_timeout or settings.SCRAPER_STEP_TIMEOUT_SECONDS
    return _build_context(url, timeout_step)

async def run_pipeline(
    url: str,
    *,
    step_timeout: Optional[float] = None,
    pipeline_timeout: Optional[float] = None,
) -> PipelineOutcome:
    """ Execute o pipeline padrão e retorna o ``PipelineOutcome`` resultante """
    timeout_step = step_timeout or settings.SCRAPER_STEP_TIMEOUT_SECONDS
    context = _build_context(url, timeout_step)
    pipeline = create_pipeline(
        step_timeout=timeout_step,
        pipeline_timeout=pipeline_timeout,
    )

    try:
        outcome = await pipeline.run(context)
    except PipelineTimeoutError as exc:
        logger.error(
            "pipeline_timeout",
            url=sanitize_log_data(url),
            timeout=pipeline_timeout or settings.SCRAPER_PIPELINE_TIMEOUT_SECONDS,
        )
        raise
        
    return outcome

__all__ = [
    "create_pipeline",
    "build_context",
    "run_pipeline",
]
