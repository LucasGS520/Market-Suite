""" Estapas básicas para o pipeline sequencial do MarketScraper

O foco é cobrir os casos estáticos mais comuns: baixar o HTML 
sincronamente e tentar extrair os campos essenciais com parsers
leves. Cada etapa retorna ``StepResult`` para o ``SynergicPipeline``
controlar fallback e métricas.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from market_scraper.parsers import (
    parse_generic_html,
    parse_with_beautifulsoup,
    parse_with_extruct,
)
from market_scraper.services.synergic_pipeline import PipelineContext, PipelineStep, StepResult


logger = structlog.get_logger("pipeline_steps")

async def download_html(url: str, *, timeout: float) -> str:
    """ Baixa o HTML usando ``httpx`` respeitando o tempo limite informado """
    headers = {"User-Agent": "marketsuite-scraper/1.0", "Accept": "text/html"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.text

class FetchHTMLStep(PipelineStep):
    """ Obtém o HTML bruto e o disponibiliza no contexto compartilhado """
    def __init__(self, *, timeout: float | None = None) -> None:
        super().__init__(name="fetch_html", timeout=timeout)

    async def run(self, context: PipelineContext) -> StepResult:
        if context.html:
            return StepResult.success(message="HTML já presente no contexto")
        
        timeout_value = self.timeout if self.timeout is not None else context.default_step_timeout
        html = await download_html(context.url, timeout=timeout_value)
        context.set_html(html)
        return StepResult.success(
            message="HTML baixado com sucesso",
        )
    
def _normalize_payload(raw: dict[str, Any] | None, context: PipelineContext) -> dict[str, Any] | None:
    """ Garante que o payload possui os campos esperados e valores preenchidos """
    if not raw:
        return None
    
    name = (raw.get("name") or "").strip()
    price = (raw.get("current_price") or "").strip()
    if not name or not price:
        return None
    return {
        "name": name,
        "current_price": price,
        "url": raw.get("url") or context.url,
        "source": raw.get("source") or context.source,
    }

class JsonLdParserStep(PipelineStep):
    """ Tenta extrair dados estruturados com a biblioteca ``extruct`` """
    def __init__(self) -> None:
        super().__init__(name="json_ld_parser")

    async def run(self, context: PipelineContext) -> StepResult:
        if not context.html:
            return StepResult.empty("HTML não disponível para extração estruturada")
        
        parsed = parse_with_extruct(context.html, context.url)
        payload = _normalize_payload(parsed, context)
        if payload:
            return StepResult.success(
                payload=payload,
                message="Metadados estruturados encontrados",
            )
        return StepResult.empty("Metadados estruturados ausentes ou incompletos")
    
class HtmlMetadataParserStep(PipelineStep):
    """ Analisa metatags e estrutura básica com BeautifulSoup """
    def __init__(self) -> None:
        super().__init__(name="html_metadata_parser")

    async def run(self, context: PipelineContext) -> StepResult:
        if not context.html:
            return StepResult.empty("HTML indisponível para extração com BeautifulSoup")
        
        parsed = parse_with_beautifulsoup(context.html, context.url)
        payload = _normalize_payload(parsed, context)
        if payload:
            return StepResult.success(
                payload=payload,
                message="Metadados HTML encontrados",
            )
        return StepResult.empty("Metadados HTML ausentes ou incompletos")

class GenericFallbackParserStep(PipelineStep):
    """ Utiliza heurísticas genéricas baseadas em seletores comuns """
    def __init__(self) -> None:
        super().__init__(name="generic_fallback_parser")

    async def run(self, context: PipelineContext) -> StepResult:
        if not context.html:
            return StepResult.empty("HTML indisponível para heurísticas genéricas")
        
        parsed = parse_generic_html(context.html, context.url)
        payload = _normalize_payload(parsed, context)
        if payload:
            return StepResult.success(
                payload=payload,
                message="Heurísticas genéricas aplicadas",
            )
        return StepResult.empty("Heurísticas genéricas não encontraram dados")
    
def default_pipeline_steps() -> list[PipelineStep]:
    """ Retorna a sequência padrão de etapas do pipeline enxuto """
    return [
        FetchHTMLStep(),
        JsonLdParserStep(),
        HtmlMetadataParserStep(),
        GenericFallbackParserStep(),
    ]

__all__ = [
    "FetchHTMLStep",
    "JsonLdParserStep",
    "HtmlMetadataParserStep",
    "GenericFallbackParserStep",
    "default_pipeline_steps",
    "download_html",
]
