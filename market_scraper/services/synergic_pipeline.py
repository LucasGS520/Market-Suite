""" Pipeline sequencial e observável para o MarktScraper

O módulo implementa uma versão enxuta do pipeline que processa etapas em
sequência, respeitando limites de tempo configuráveis e registrando
métricas por etapa. A execução linear com métricas grante previsibilidade
e observabilidade para o serviço de scraping.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Literal, Sequence

import structlog

from shared.metrics.metrics_scraper import (
    SCRAPER_NO_RESULT_TOTAL,
    SCRAPER_STEP_FALLBACK_TOTAL,
    SCRAPER_STEP_LATENCY_SECONDS,
    SCRAPER_STEP_SUCCESS_TOTAL,
)
from shared.utils.logging_utils import sanitize_log_data


#Logger estruturado para acompanhamento dos eventos do pipeline
#Convenção: logs do pipeline sempre carregam os campos ``domain``, ``result`` e ``duration_ms``
logger = structlog.get_logger("scraper_pipeline")

@dataclass
class PipelineContext:
    """ Armazena dados compartilhados entre as etapas do pipeline """
    url: str
    source: str
    default_step_timeout: float
    html: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """ Inicializa chaves mínimas do ``shared_context``
        
        Garante que as etapas sempre encontrem informações básicas
        sem depender de inicialização externa.
        """
        self.data.setdefault("url", self.url)
        self.data.setdefault("source", self.source)
        self.data.setdefault("domain", self.source)
        self.data.setdefault("step_timeout", self.default_step_timeout)

    def set_html(self, html: str) -> None:
        """ Guarda o HTML obtido para que etapas posteriores possam reutilizá-lo """
        self.html = html

    def build_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """ Normaliza o payload principal adicionando origem e URL canônica """
        return {
            "name": payload.get("name", ""),
            "current_price": payload.get("current_price", ""),
            "url": payload.get("url") or self.url,
            "source": payload.get("source") or self.source,
        }
    
@dataclass
class StepResult:
    """ Representa o resultado de uma etapa do pipeline """
    status: Literal["success", "empty", "error"]
    payload: dict[str, Any] | None = None
    message: str | None = None

    @classmethod
    def success(cls, payload: dict[str, Any] | None = None, message: str | None = None) -> "StepResult":
        """ Facilita a criação de um resultado de sucesso """
        return cls(status="success", payload=payload, message=message)
    
    @classmethod
    def empty(cls, message: str | None = None) -> "StepResult":
        """ Indica que a etapa executou mas não encontrou dados úteis """
        return cls(status="empty", payload=None, message=message)
    
    @classmethod
    def failure(cls, message: str | None = None) -> "StepResult":
        """ Representa falha não recuperável na etapa atual """
        return cls(status="error", payload=None, message=message)
    
@dataclass
class StepExecution:
    """ Registro de execução de uma etapa para depuração e métricas """
    name: str
    status: str
    duration_seconds: float
    message: str | None = None

@dataclass
class PipelineOutcome:
    """ Guarda o resumo da execução do pipeline """
    status: Literal["success", "no_result", "timeout", "error"]
    context: PipelineContext
    payload: dict[str, Any] | None = None
    steps: list[StepExecution] = field(default_factory=list)

class PipelineError(Exception):
    """ Erro genérico emitido quando a execução do pipeline falha """

class PipelineTimeoutError(PipelineError):
    """ Erro emitido quando o tempo máximo do pipeline é excedido """

class PipelineStep:
    """ Classe base para todas as etapas do pipeline sequencial """
    def __init__(self, *, name: str | None = None, timeout: float | None = None) -> None:
        self._name = name or self.__class__.__name__
        self.timeout = timeout

    @property
    def name(self) -> str:
        """ Retorna o nome público da etapa """
        return self._name
    
    async def run(self, context: PipelineContext) -> StepResult:
        """ Executa a etapa e retorna um ``StepResult`` com o desfecho """
        raise NotImplementedError

class SynergicPipeline:
    """ Executa etapas em sequência, monitorando métricas e timeouts """
    def __init__(
        self,
        steps: Sequence[PipelineStep],
        *,
        step_timeout: float,
        pipeline_timeout: float,
    ) -> None:
        self._steps: list[PipelineStep] = list(steps)
        self._default_step_timeout = step_timeout
        self._pipeline_timeout = pipeline_timeout

    async def run(self, context: PipelineContext) -> PipelineOutcome:
        """ Percorre as etapas em ordem até encontrar um payload válido """
        executions: list[StepExecution] = []
        payload: dict[str, Any] | None = None
        status: Literal["success", "no_result", "timeout", "error"] = "no_result"
        #Controle de rótulos garante consistência entre métricas de etapa e do pipeline
        last_result_label: str = "no_result"
        final_result_label: str = "no_result"
        context.data.setdefault("pipeline_timeout", self._pipeline_timeout)
        context.data.setdefault("step_timeout", context.default_step_timeout)

        async def _run_sequence() -> None:
            nonlocal payload, status, last_result_label
            for step in self._steps:
                timeout_value = step.timeout if step.timeout is not None else context.default_step_timeout
                start = perf_counter()
                try:
                    result = await asyncio.wait_for(step.run(context), timeout=timeout_value)
                except asyncio.TimeoutError:
                    duration = perf_counter() - start
                    result_label = "timeout"
                    executions.append(
                        StepExecution(
                            name=step.name,
                            status="timeout",
                            duration_seconds=duration,
                            message="Tempo limite da etapa excedido",
                        )
                    )
                    SCRAPER_STEP_LATENCY_SECONDS.labels(step.name, context.source, result_label).observe(duration)
                    SCRAPER_STEP_FALLBACK_TOTAL.labels(step.name, context.source, result_label).inc()
                    last_result_label = result_label
                    logger.warning(
                        "step_timeout",
                        step=step.name,
                        duration_ms=int(duration * 1000),
                        timeout=timeout_value,
                        url=sanitize_log_data(context.url),
                        domain=context.source,
                        result=result_label,
                    )
                    continue
                except Exception as exc:
                    duration = perf_counter() - start
                    result_label = "error"
                    executions.append(
                        StepExecution(
                            name=step.name,
                            status="error",
                            duration_seconds=duration,
                            message="Falha interna na etapa",
                        )
                    )
                    SCRAPER_STEP_LATENCY_SECONDS.labels(step.name, context.source, result_label).observe(duration)
                    SCRAPER_STEP_FALLBACK_TOTAL.labels(step.name, context.source, result_label).inc()
                    last_result_label = result_label
                    logger.exception(
                        "step_error",
                        step=step.name,
                        duration_ms=int(duration * 1000),
                        url=sanitize_log_data(context.url),
                        domain=context.source,
                        result=result_label,
                        error=sanitize_log_data(str(exc)),
                    )
                    continue

                duration = perf_counter() - start
                result_label = result.status
                SCRAPER_STEP_LATENCY_SECONDS.labels(step.name, context.source, result_label).observe(duration)
                last_result_label = result_label

                if result.status == "success":
                    SCRAPER_STEP_SUCCESS_TOTAL.labels(step.name, context.source, result_label).inc()
                    executions.append(
                        StepExecution(
                            name=step.name,
                            status="success",
                            duration_seconds=duration,
                            message=result.message,
                        )
                    )
                    if result.payload:
                        payload = context.build_payload(result.payload)
                        status = "success"
                        return
                    continue
                
                SCRAPER_STEP_FALLBACK_TOTAL.labels(step.name, context.source, result_label).inc()
                executions.append(
                    StepExecution(
                        name=step.name,
                        status=result.status,
                        duration_seconds=duration,
                        message=result.message,
                    )
                )

        pipeline_start = perf_counter()    
        try:
            await asyncio.wait_for(_run_sequence(), timeout=self._pipeline_timeout)
        except asyncio.TimeoutError as exc:
            final_result_label = "timeout"
            logger.error(
                "pipeline_timeout",
                timeout=self._pipeline_timeout,
                url=sanitize_log_data(context.url),
                step_count=len(self._steps),
                duration_ms=int((perf_counter() - pipeline_start) * 1000),
                domain=context.source,
                result=final_result_label,
            )
            SCRAPER_NO_RESULT_TOTAL.labels(context.source, final_result_label).inc()
            raise PipelineTimeoutError("Tempo limite do pipeline excedido") from exc
        
        if status != "success":
            #Mapeia o último estado observado para um rótulo padronizado de resultado final
            if last_result_label in {"empty", "success", "no_result"}:
                final_result_label = "no_result"
            elif last_result_label in {"timeout", "error"}:
                final_result_label = last_result_label
            else:
                final_result_label = "error"
                logger.warning(
                    "unknown_result_label",
                    last_result=last_result_label,
                    domain=context.source,
                    url=sanitize_log_data(context.url),
                    result=final_result_label,
                )
            SCRAPER_NO_RESULT_TOTAL.labels(context.source, final_result_label).inc()
            
        return PipelineOutcome(
            status=status,
            payload=payload,
            steps=executions,
            context=context,
        )

__all__ = [
    "PipelineContext",
    "StepExecution",
    "PipelineOutcome",
    "PipelineError",
    "PipelineTimeoutError",
    "PipelineStep",
    "SynergicPipeline",
    "StepResult",
]
