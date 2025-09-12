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
    
class SynergicPipeline:
    """ Orquestra a execução das etapas definidas """
    def __init__(
            self, 
            steps: list[PipelineStep], 
            *, 
            execution_mode: Literal["sequential", "parallel", "conditional"] = "sequential",
        ) -> None:
        """ Cria um pipeline sinégico
        
        ``steps`` é a lista de etapas que será executada. ``execution_mode``
        define como o pipeline será processado: ``sequential`` (padrão),
        ``parallel`` ou ``conditional``.
        """
        self.steps = steps
        self.execution_mode = execution_mode

    async def run(self, shared_context: dict[str, Any] | None = None) -> dict[str, Any]:
        """ Executa o pipeline retornando os resultados e o contexto final """
        shared_context = shared_context or {}
        results: list[dict[str, Any]] = []

        async def _run_step(step: PipelineStep) -> dict[str, Any]:
            result = await step.run(shared_context)
            ctx = result.get("shared_context")
            if isinstance(ctx, dict):
                shared_context.update(ctx)
            return result
        
        if self.execution_mode == "parallel":
            execs = [_run_step(step) for step in self.steps]
            results = await asyncio.gather(*execs)
        else:
            for step in self.steps:
                if self.execution_mode == "conditional" and not step.should_run(shared_context):
                    continue
                results.append(await _run_step(step))

        return {"results": results, "shared_context": shared_context}

  
__all__ = ["PipelineStep", "SynergicPipeline"]
