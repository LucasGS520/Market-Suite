from __future__ import annotations

""" Pipeline sinérgico para orquestrar etapas de scraping

Este módulo define uma estrutura genérica de pipeline onde cada etapa
pode compartilhar e atualizar um ``shared_context``. O objetivo é
permitir que múltiplas bibliotecas de parsing/extração trabalhem de
forma coordenada, mantendo o código modular e extensível.
"""

from abc import ABC, abstractmethod
from typing import Any, Literal
import asyncio
from time import perf_counter

import structlog

from shared.metrics.metrics_scraper import (
    SCRAPER_STRATEGY_TOTAL,
    SCRAPER_FALLBACK_TOTAL,
    SCRAPING_LATENCY_SECONDS,
)
from shared.utils.logging_utils import sanitize_log_data
from market_scraper.utils.data_quality_validator import DataQualityValidator


class PipelineStep(ABC):
    """ Representa uma etapa do pipeline de scraping """

    @abstractmethod
    async def run(self, shared_context: dict[str, Any]) -> dict[str, Any]:
        """ Executa a etapa e retorna um dicionário de resultados
        
        O retorno pode conter ``shared_context`` para ser mesclado ao
        contexto principal e quaisquer dados intermediários obtidos.
        """
        raise NotImplementedError
    
    def should_run(self, shared_context: dict[str, Any]) -> bool:
        """ Determina se a etapa deve ser executada no modo condicional """
        return True
    
logger = structlog.get_logger("synergic_pipeline")


class SynergicPipeline:
    """ Orquestra a execução das etapas definidas """
    def __init__(
        self,
        steps: list[PipelineStep],
        *,
        execution_mode: Literal["sequential", "parallel", "conditional"] = "sequential",
        validator: DataQualityValidator | None = None,
    ) -> None:
        """ Cria um pipeline sinérgico
        
        ``steps`` é a lista de etapas que será executada. ``execution_mode``
        define como o pipeline será processado: ``sequential`` (padrão),
        ``parallel`` ou ``conditional``. ``validator`` permite substituir o
        :class:`DataQualityValidator` padrão, concentrando a validação das
        saídas de parsing no pipeline.
        """
        self.steps = steps
        self.execution_mode = execution_mode
        self.validator = validator or DataQualityValidator()

    async def run(
        self, 
        shared_context: dict[str, Any] | None = None,
        execution_mode: Literal["sequential", "parallel", "conditional"] | None = None,    
    ) -> dict[str, Any]:
        """ Executa o pipeline retornando os resultados e o contexto final """
        shared_context = shared_context or {}
        results: list[dict[str, Any]] = []
        mode = execution_mode or self.execution_mode

        async def _run_step(step: PipelineStep) -> tuple[str, dict[str, Any], str]:
            """ Executa uma etapa registrando métricas e validação """
            step_name = step.__class__.__name__
            start = perf_counter()
            try:
                result = await step.run(shared_context)
            except Exception as err:
                logger.exception("pipeline_step_error", step=step_name, error=sanitize_log_data(str(err)))
                result = {"status": "error"}
            duration = perf_counter() - start

            status = result.get("status") or "error"
            details = result.get("details")
            if isinstance(details, dict):
                try:
                    self.validator.validate(details)
                except ValueError as validation_error:
                    status = "invalid"
                    result = {
                        **result,
                        "status": status,
                        "validation_error": str(validation_error),
                    }
                    logger.info(
                        "step_validation_failed",
                        step=step_name,
                        error=sanitize_log_data(str(validation_error)),
                    )
            if result.get("status") != status:
                result = {**result, "status": status}

            ctx = result.get("shared_context")
            if isinstance(ctx, dict):
                shared_context.update(ctx)

            SCRAPER_STRATEGY_TOTAL.labels(step_name, status).inc()
            SCRAPING_LATENCY_SECONDS.labels(step_name).observe(duration)

            logger.info(
                "step_completed", 
                step=step_name, 
                status=status, 
                execution_time=duration, 
                details=sanitize_log_data(result.get("details")),
            )
            return step_name, result, status
        
        success_status = {"success", "ok", "NOT_MODIFIED"}

        if mode == "parallel":
            execs = [_run_step(step) for step in self.steps]
            responses = await asyncio.gather(*execs)
            for step_name, resp, status in responses:
                results.append(resp)
                if status not in success_status:
                    SCRAPER_FALLBACK_TOTAL.inc()
                    logger.info("fallback_triggered", step=step_name)

        else:
            for idx, step in enumerate(self.steps):
                if mode == "conditional" and not step.should_run(shared_context):
                    SCRAPER_FALLBACK_TOTAL.inc()
                    logger.info("step_skipped", step=step.__class__.__name__)
                    continue

                step_name, resp, status = await _run_step(step)
                results.append(resp)
                if status not in success_status and idx < len(self.steps) - 1:
                    SCRAPER_FALLBACK_TOTAL.inc()
                    logger.info("fallback_triggered", step=step_name)

        primary_with_details = next(
            (
                item
                for item in results
                if item.get("status") in success_status and item.get("details")
            ),
            None,
        )
        primary = primary_with_details or next(
            (
                item
                for item in results
                if item.get("status") in success_status
            ),
            None,
        )

        outcome: dict[str, Any] = {
            "results": results,
            "shared_context": shared_context,
            "status": primary.get("status") if primary else "error",
        }

        if primary_with_details:
            details = primary_with_details.get("details")
            if details is not None:
                outcome["details"] = details
            if primary_with_details.get("extraction_method"):
                outcome["extraction_method"] = primary_with_details.get("extraction_method")

        return outcome

  
__all__ = ["PipelineStep", "SynergicPipeline"]
