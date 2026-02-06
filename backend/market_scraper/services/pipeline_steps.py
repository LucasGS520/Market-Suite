""" Etapas básicas para o pipeline sequencial do MarketScraper

O módulo declara unicamente as etapas que compõem o pipeline padrão.
Cada ``PipelineStep`` delega responsabilidade específica para módulos
auxiliares (download, parsers e validação), mantendo este arquivo
focado na orquestração das dependências entre etapas.
"""

from __future__ import annotations

import httpx
import structlog

from market_scraper.core.config_scraper import settings
from market_scraper.parsers import (
    parse_generic_html,
    parse_with_beautifulsoup,
    parse_with_extruct,
)
from market_scraper.parsers.domain_parsers import get_domain_parser
from market_scraper.services.parser_runner import (
    ParserCallable,
    run_parser_with_validation,
)
from market_scraper.services.synergic_pipeline import (
    PipelineContext,
    PipelineStep,
    StepResult,
)
from market_scraper.utils.availability import detect_availability
from market_scraper.utils import cache, robots, singleflight
from market_scraper.utils.http_download import download_html, extract_domain


logger = structlog.get_logger("scraper_pipeline_steps")

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

        #Validação de robots.txt ocorre antes de qualquer tentativa de download para respeitar políticas públicas dos sites
        if not await robots.is_allowed(context.url, timeout=timeout_value):
            return StepResult.failure(message="unsupported_by_robots")
        
        #Quando o orquestrador força refresh, ignoramos o cache para garantir HTML atualizado
        if not context.force_refresh:
            cached_html: str | None = cache.get(context.url)
            if cached_html is not None:
                context.set_html(cached_html)
                return StepResult.success(message="html_from_cache")

        async def _download() -> str:
            """ Encapsula o download respeitando timeout da etapa para coalescing """
            return await download_html(context.url, timeout=timeout_value)
        
        #O singleflight também usa a mesma URL para coalescer chamadas simultâneas
        try:
            html = await singleflight.coalesce(context.url, _download)
            context.data["http_status"] = context.data.get("http_status") or 200
        except httpx.TooManyRedirects as exc:
            #Marcamos explicitamente a falha para evitar loops em URLs com redirecionamento infinito
            context.data["http_status"] = context.data.get("http_status") or 422
            logger.warning(
                "html_fetch_redirect_loop",
                url=context.url,
                domain=context.source,
                error=str(exc),
            )
            return StepResult.failure(message="too_many_redirects")
        except (httpx.InvalidURL, httpx.UnsupportedProtocol) as exc:
            #Tratamos falhas de URL malformada ou protocolo inválido para sinalizar revisão manual
            context.data["http_status"] = context.data.get("http_status") or 422
            logger.warning(
                "html_fetch_invalid_url",
                url=context.url,
                domain=context.source,
                error=str(exc),
            )
            return StepResult.failure(message="invalid_url")
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            context.data["http_status"] = status_code
            availability, last_status = detect_availability(
                None,
                status_code=status_code,
                domain=context.source,
            )
            if availability is False:
                logger.info(
                    "html_fetch_unavailable",
                    url=context.url,
                    status_code=status_code,
                    last_status=last_status,
                )
                context.set_html("")
                context.data["availability"] = availability
                context.data["last_status"] = last_status
                context.data["availability_inferred"] = availability
                context.data["last_status_inferred"] = last_status
                return StepResult.success(
                    payload={
                        "name": None,
                        "current_price": None,
                        "url": context.url,
                        "source": context.source,
                        "availability": availability,
                        "last_status": last_status,
                    },
                    message="Disponibilidade inferida por código HTTP",
                )
            raise
        context.set_html(html)
        #Armazenamos o HTML recém obtido para acelerar futuras requisições
        cache.set(context.url, html, settings.SCRAPER_CACHE_TTL_SECONDS)
        return StepResult.success(message="HTML baixado com sucesso")
    
class _BaseParserStep(PipelineStep):
    """ Implementa o fluxo padrão para etapas de parsing 
    
    Consome: ``context.html`` e ``context.url``
    Produz: ``context.data['name']``, ``context.data['current_price']``,
    ``context.data['url']`` e ``context.data['source']``
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
        
        ok, payload = run_parser_with_validation(
            parser=self._parser,
            context=context,
            step_name=self.name,
        )
        if ok and payload:
            return StepResult.success(payload=payload, message=self._success_message)
        return StepResult.empty(self._empty_message)
    
class JsonLdParserStep(_BaseParserStep):
    """ Tenta extrair dados estruturados em JSON-LD """
    def __init__(self) -> None:
        super().__init__(
            name="json_ld_parser",
            parser=parse_with_extruct,
            success_message="Metadados estruturados encontrados",
            empty_message="Metadados estruturados ausentes ou incompletos",
            missing_html_message="HTML indisponível para extração de dados estruturados",
        )

class HtmlMetadataParserStep(_BaseParserStep):
    """ Analisa metatags e estrutura básica em BeautifulSoup """
    def __init__(self) -> None:
        super().__init__(
            name="html_metadata_parser",
            parser=parse_with_beautifulsoup,
            success_message="Metadados HTML extraídos com sucesso",
            empty_message="Metadados HTML ausentes ou inválidos",
            missing_html_message="HTML indisponível para extração com BeautifulSoup",
        )

class GenericFallbackParserStep(_BaseParserStep):
    """ Aplica heurísticas genéricas quando as demais estapas falham """
    def __init__(self) -> None:
        super().__init__(
            name="generic_fallback_parser",
            parser=parse_generic_html,
            success_message="Heurísticas genéricas aplicadas",
            empty_message="Heurísticas genéricas não encontraram dados",
            missing_html_message="HTML indisponível para heurísticas genéricas",
        )

class DomainSpecificParserStep(PipelineStep):
    """ Executa parsers dedicados aos marketplaces conhecidos pelo serviço """
    def __init__(self, *, timeout: float | None = None) -> None:
        super().__init__(name="domain_specific_parser", timeout=timeout)
    
    async def run(self, context: PipelineContext) -> StepResult:
        if not context.html:
            return StepResult.empty("HTML indisponível para parser específico de domínio")
        
        domain = context.source or extract_domain(context.url) or ""
        matched = get_domain_parser(domain)
        if not matched:
            return StepResult.empty("Domínio sem parser dedicado")
        
        suffix, parser = matched
        ok, payload = run_parser_with_validation(
            parser=parser,
            context=context,
            step_name=self.name,
        )
        if ok and payload:
            #Guardamos o sufixo aplicado para debugar cenários de múltiplas tentativas
            context.data.setdefault("domain_parser_suffix", suffix)
            return StepResult.success(
                payload=payload,
                message=f"Parser específico aplicado para {suffix}",
            )
        return StepResult.empty("Parser específico não retornou dados válidos")
    
def default_pipeline_steps() -> list[PipelineStep]:
    """ Retorna a sequência padrão de etapas do pipeline enxuto """
    steps: list[PipelineStep] = [
        FetchHTMLStep(),
        JsonLdParserStep(),
        HtmlMetadataParserStep(),
        DomainSpecificParserStep(),
        GenericFallbackParserStep(),
    ]
    #Mantemos a ordem fixa para cumprir pipeline mínimo definido
    return steps

__all__ = [
    "FetchHTMLStep",
    "JsonLdParserStep",
    "HtmlMetadataParserStep",
    "DomainSpecificParserStep",
    "GenericFallbackParserStep",
    "default_pipeline_steps",
]
