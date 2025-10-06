""" Etapas básicas para o pipeline sequencial do MarketScraper

O módulo concentra a execução linear das etapas responsáveis por baixar
HTML e extrair o payload mínimo. Cada ``PipelineStep`` descreve quais
chaves do ``shared_context`` consome e quais atualiza, reduzindo efeitos
colaterais e facilitando testes.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import httpx
import structlog

from shared.utils.logging_utils import sanitize_log_data

from market_scraper.core.config_scraper import settings
from market_scraper.parsers import (
    parse_generic_html,
    parse_with_beautifulsoup,
    parse_with_extruct,
    parse_with_requests_html,
)
from market_scraper.services.synergic_pipeline import PipelineContext, PipelineStep, StepResult
from market_scraper.utils.validator import DataQualityValidator


logger = structlog.get_logger("pipeline_steps")
ParserCallable = Callable[[str, str], Mapping[str, Any] | None]
_validator = DataQualityValidator()

def _update_shared_payload(context: PipelineContext, payload: Mapping[str, str]) -> None:
    """ Atualiza o ``shared_context`` apenas com campos oficializados pelo contrato """
    #Os parsers nunca modificam o contexto diretamente; concentra aqui as atualizações
    context.data["name"] = payload["name"]
    context.data["current_price"] = payload["current_price"]
    context.data["url"] = payload["url"]
    context.data["source"] = payload["source"]
    context.data["payload"] = dict(payload)

def _run_parser_with_validation(
    *,
    parser: ParserCallable,
    context: PipelineContext,
    step_name: str,
) -> tuple[bool, dict[str, str] | None]:
    """ Executa parser, valida resultado e sincroniza o ``shared_context`` """
    html = context.html or ""
    try:
        raw_payload = parser(html, context.url)
    except Exception as exc:
        logger.warning(
            "parser_execution_error",
            step=step_name,
            domain=context.source,
            duration_ms=0.0,
            result="error",
            url=sanitize_log_data(context.url),
            error=sanitize_log_data(str(exc)),
        )
        return False, None
    
    if not raw_payload:
        return False, None
    
    validated = _validator.validate(
        step_name=step_name,
        payload=raw_payload,
        url=context.url,
        source=context.source,
    )
    if not validated:
        return False, None
    
    _update_shared_payload(context, validated)
    return True, validated

async def download_html(url: str, *, timeout: float) -> str:
    """ Baixa o HTML usando ``httpx`` com limites rígidos de segurança """
    headers = {"User-Agent": "marketsuite-scraper/1.0", "Accept": "text/html"}
    
    client_timeout = httpx.Timeout(
        timeout,
        connect=min(timeout, settings.SCRAPER_HTTP_TIMEOUT_CONNECT),
        read=min(timeout, settings.SCRAPER_HTTP_TIMEOUT_READ),
        write=min(timeout, settings.SCRAPER_HTTP_TIMEOUT_WRITE),
        pool=settings.SCRAPER_HTTP_TIMEOUT_POOL,
    )
    limits = httpx.Limits(
        max_connections=settings.SCRAPER_HTTP_MAX_CONNECTIONS,
        max_keepalive_connections=settings.SCRAPER_HTTP_MAX_KEEPALIVE,
    )

    async with httpx.AsyncClient(
        timeout=client_timeout,
        follow_redirects=True,
        limits=limits,
        max_redirects=settings.SCRAPER_HTTP_MAX_REDIRECTS,
    ) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()

        content = response.content
        if len(content) > settings.SCRAPER_HTTP_MAX_CONTENT_LENGTH:
            raise ValueError("Resposta excedeu o tamanho máximo permitido")

        #Retornamos o texto decodificado após validar o tamanho bruto para evitar ataques de payload gigante
        return response.text

class FetchHTMLStep(PipelineStep):
    """ Obtém o HTML bruto e o disponibiliza no contexto compartilhado 
    
    Consome: ``context.url``
    Produz: ``context.html``
    """
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
    
class _BaseParserStep(PipelineStep):
    """ Implementa o fluxo padrão para etapas de parsing 
    
    Consome: ``context.html`` e ``context.url``
    Produz: ``context.data['name']``, ``context.data['current_price']``, ``context.data['url']`` e ``context.data['source']``
    """
    def __init__(
        self,
        *,
        name: str,
        parser: ParserCallable,
        success_message: str,
        empty_message: str,
        missing_html_message: str,
        timeout: float | None = None,
    ) -> None:
        super().__init__(name=name, timeout=timeout)
        self._parser = parser
        self._success_message = success_message
        self._empty_message = empty_message
        self._missing_html_message = missing_html_message

    async def run(self, context: PipelineContext) -> StepResult:
        if not context.html:
            return StepResult.empty(self._missing_html_message)
        
        ok, payload = _run_parser_with_validation(
            parser=self._parser,
            context=context,
            step_name=self.name,
        )
        if ok and payload:
            return StepResult.success(payload=payload, message=self._success_message)
        return StepResult.empty(self._empty_message)
    
class JsonLdParserStep(_BaseParserStep):
    """ Tenta extrair dados estruturados em JSON-LD
    
    Consome: ``context.html``
    Produz: ``context.data['payload']`` com dados validados
    """
    def __init__(self) -> None:
        super().__init__(
            name="json_ld_parser",
            parser=parse_with_extruct,
            success_message="Metadados estruturados encontrados",
            empty_message="Metadados estruturados ausentes ou incompletos",
            missing_html_message="HTML indisponível para extração de dados estruturados",
        )

class HtmlMetadataParserStep(_BaseParserStep):
    """ Analisa metatags e estrutura básica em BeautifulSoup 
    
    Consome: ``context.html``
    Produz: ``context.data['payload']``
    """
    def __init__(self) -> None:
        super().__init__(
            name="html_metadata_parser",
            parser=parse_with_beautifulsoup,
            success_message="Metadados HTML extraídos com sucesso",
            empty_message="Metadados HTML ausentes ou inválidos",
            missing_html_message="HTML indisponível para extração com BeautifulSoup",
        )

class GenericFallbackParserStep(_BaseParserStep):
    """ Aplica heurísticas genéricas quando as demais estapas falham 
    
    Consome: ``context.html``
    Produz: ``context.data['payload']``
    """
    def __init__(self) -> None:
        super().__init__(
            name="generic_fallback_parser",
            parser=parse_generic_html,
            success_message="Heurísticas genéricas aplicadas",
            empty_message="Heurísticas genéricas não encontraram dados",
            missing_html_message="HTML indisponível para heurísticas genéricas",
        )

class RequestsHtmlParserStep(_BaseParserStep):
    """ Utiliza Requests-HTML para interpretar páginas com markup dinâmico
    
    Consome: ``context.html``
    Produz: ``context.data['payload']``
    """
    def __init__(
        self,
        *,
        timeout: float | None = None,
    ) -> None:
        super().__init__(
            name="requests_html_parser",
            parser=parse_with_requests_html,
            success_message="Dados extraídos com Requests-HTML",
            empty_message="Requests-HTML não encontrou dados",
            missing_html_message="HTML indisponível para Requests-HTML",
            timeout=timeout,
        )
    
def default_pipeline_steps() -> list[PipelineStep]:
    """ Retorna a sequência padrão de etapas do pipeline enxuto """
    steps: list[PipelineStep] = [
        FetchHTMLStep(),
        JsonLdParserStep(),
        HtmlMetadataParserStep(),
    ]
    if settings.SCRAPER_ENABLE_REQUESTS_HTML:
        steps.append(
            RequestsHtmlParserStep(
                timeout=settings.SCRAPER_REQUESTS_HTML_TIMEOUT_SECONDS,
            )
        )
    steps.append(GenericFallbackParserStep())
    return steps

__all__ = [
    "FetchHTMLStep",
    "JsonLdParserStep",
    "HtmlMetadataParserStep",
    "GenericFallbackParserStep",
    "RequestsHtmlParserStep",
    "default_pipeline_steps",
    "download_html",
]
