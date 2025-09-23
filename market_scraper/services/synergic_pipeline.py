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
            except asyncio.CancelledError:
                duration = perf_counter() - start
                SCRAPER_STRATEGY_TOTAL.labels(step_name, "cancelled").inc()
                SCRAPING_LATENCY_SECONDS.labels(step_name).observe(duration)
                logger.info(
                    "step_cancelled",
                    step=step_name,
                    execution_time=duration,
                )
                raise
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
            task_to_index: dict[asyncio.Task[tuple[str, dict[str, Any], str]], int] = {}
            results_by_index: dict[int, dict[str, Any]] = {}
            cancelled_steps: list[str] = []
            first_success_detected = False

            for index, step in enumerate(self.steps):
                task = asyncio.create_task(_run_step(step))
                task_to_index[task] = index

            pending_tasks: set[asyncio.Task[tuple[str, dict[str, Any], str]]] = set(task_to_index.keys())

            while pending_tasks:
                done, pending_tasks = await asyncio.wait(pending_tasks, return_when=asyncio.FIRST_COMPLETED)

                for finished in done:
                    index = task_to_index.pop(finished, None)
                    if index is None:
                        continue

                    try:
                        step_name, resp, status = finished.result()
                        results_by_index[index] = resp

                        if status in success_status:
                            if not first_success_detected:
                                first_success_detected = True
                                logger.info(
                                    "parallel_pipeline_first_success",
                                    step=step_name,
                                    status=status,
                                )
                                for pending in pending_tasks:
                                    pending.cancel()
                        else:
                            SCRAPER_FALLBACK_TOTAL.inc()
                            logger.info("fallback_triggered", step=step_name)
                    except asyncio.CancelledError:
                        cancelled_steps.append(self.steps[index].__class__.__name__)
                        results_by_index[index] = {"status": "cancelled"}

            if cancelled_steps:
                logger.info("parallel_cancelled_steps", steps=cancelled_steps)

            results = [
                results_by_index[idx]
                for idx in range(len(self.steps))
                if idx in results_by_index
            ]

        else:
            for idx, step in enumerate(self.steps):
                if mode == "conditional" and not step.should_run(shared_context):
                    SCRAPER_FALLBACK_TOTAL.inc()
                    logger.info("step_skipped", step=step.__class__.__name__)
                    continue

                step_name, resp, status = await _run_step(step)
                results.append(resp)
                
                if status in success_status:
                    #Interrompe o pipeline imediatamente após o primeiro sucesso
                    if idx < len(self.steps) - 1:
                        logger.info(
                            "pipeline_short_circuit",
                            step=step_name,
                            status=status,
                        )
                    break

                if idx < len(self.steps) - 1:
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
