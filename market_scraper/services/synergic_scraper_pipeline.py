from __future__ import annotations

""" Orquestrador de etapas de scraping baseadas em ``PipelineStep``

Esta classe utiliza as etapas definidas em ``pipeline_steps`` e a
configuração de ``pipeline_policy`` para executar um pipeline
configurável por domínio. Após cada etapa os dados são validados
e em caso de falha, a próxima etapa é acionada automaicamente.
"""

from typing import Any, Iterable, Literal
import asyncio

from market_scraper.utils.data_quality_validator import DataQualityValidator
from .synergic_pipeline import PipelineStep
from .pipeline_policy import steps_for


class SynergicScraperPipeline:
    """ Executa um pipeline de scraping com fallback e validação """
    def __init__(self, *, validator: DataQualityValidator | None = None) -> None:
        self.validator = validator or DataQualityValidator()

    async def run(
            self,
            *,
            url: str,
            page_type: str = "default",
            steps: Iterable[PipelineStep] | None = None,
            execution_mode: Literal["sequential", "parallel", "conditional"] = "sequential",
            shared_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """ Executa o pipeline e retorna o primeiro resultado válido
        
        ``steps`` permite injetar etapas customizadas. Quando ausente, as
        etapas são carregadas a partir da configuração do domínio.
        ``shared_context`` é propagado entre as etapas para permitir
        reutilização de HTML, cookies ou dados intermediários.
        """
        shared_context = shared_context or {}
        shared_context.setdefault("url", url)
        steps = list(steps) if steps is not None else steps_for(url, page_type)

        if execution_mode == "parallel":
            tasks = [s.run(shared_context) for s in steps if s.should_run(shared_context)]
            responses = await asyncio.gather(*tasks)
            for resp in responses:
                details = resp.get("details")
                if isinstance(details, dict):
                    try:
                        self.validator.validate(details)
                        resp.setdefault("shared_context", shared_context)
                        return resp
                    except ValueError:
                        continue   
            return {"status": "error", "shared_context": shared_context}
        
        results = []
        for step in steps:
            if execution_mode == "conditional" and not step.should_run(shared_context):
                continue
            resp = await step.run(shared_context)
            ctx_update = resp.get("shared_context")
            if isinstance(ctx_update, dict):
                shared_context.update(ctx_update)
            results.append(resp)
            details = resp.get("details")
            if isinstance(details, dict):
                try:
                    self.validator.validate(details)
                    resp.setdefault("shared_context", shared_context)
                    return resp
                except ValueError:
                    continue
        return {"status": "error", "shared_context": shared_context, "results": results}
    
__all__ = ["SynergicScraperPipeline"]
