""" Etapas básicas para o pipeline sequencial do MarketScraper

O módulo declara unicamente as etapas que compõem o pipeline padrão.
Cada ``PipelineStep`` delega responsabilidade específica para módulos
auxiliares (download, parsers e validação), mantendo este arquivo
focado na orquestração das dependências entre etapas.
"""

from __future__ import annotations

from market_scraper.core.config_scraper import settings
from market_scraper.parsers import (
    parse_generic_html,
    parse_with_beautifulsoup,
    parse_with_extruct,
)
from market_scraper.parsers.domain_parsers import get_domain_parser
from market_scraper.services.parser_runner import ParserCallable, run_parser_with_validation
from market_scraper.services.synergic_pipeline import (
    PipelineContext,
    PipelineStep,
    StepResult,
)
from market_scraper.services.fetch_decision_gate import FetchStatus, fetch_decision_gate
from market_scraper.utils import cache, robots
from market_scraper.utils.http_download import extract_domain

class FetchHTMLStep(PipelineStep):
    """ Obtém o HTML bruto e o disponibiliza no contexto compartilhado.

    Consome: ``context.url``, ``context.source``
    Produz: ``context.html``, telemetria em ``context.data``

    Responsabilidade exclusiva desta etapa:
        1. Robots.txt check.
        2. Cache hit → retorno imediato.
        3. Delegar decisão e fetch ao ``FetchDecisionGate``.
        4. Mapear ``FetchResult`` → ``StepResult`` e atualizar contexto.
    """

    def __init__(self, *, timeout: float | None = None) -> None:
        super().__init__(name="fetch_html", timeout=timeout)

    async def run(self, context: PipelineContext) -> StepResult:
        if context.html:
            return StepResult.success(message="HTML já presente no contexto")

        timeout_value = self.timeout if self.timeout is not None else context.default_step_timeout
        domain = context.source or extract_domain(context.url) or ""

        # ── 1. Robots.txt ─────────────────────────────────────────────────
        if not await robots.is_allowed(context.url, timeout=timeout_value):
            return StepResult.failure(message="unsupported_by_robots")

        # ── 2. Cache ──────────────────────────────────────────────────────
        if context.should_use_cache("html"):
            cached_html: str | None = cache.get(context.url)
            if cached_html is not None:
                context.set_html(cached_html)
                return StepResult.success(message="html_from_cache")

        # ── 3. Delega decisão ao FetchDecisionGate ────────────────────────
        result = await fetch_decision_gate.fetch_with_fallback(
            context.url,
            domain=domain,
            force_refresh=context.force_refresh,
            timeout=timeout_value,
        )

        # ── 4. Telemetria no contexto ─────────────────────────────────────
        context.data["http_status"] = result.http_status
        context.data["layer_used"] = result.layer_used
        context.data["fallback_taken"] = result.fallback_taken
        context.data["anti_bot_detected"] = result.anti_bot_detected
        context.data["anti_bot_pattern"] = result.anti_bot_pattern
        context.data["anti_bot_bypassed"] = result.anti_bot_bypassed
        context.data["classification_reason"] = result.classification_reason

        # ── 5. Mapear FetchResult → StepResult ───────────────────────────
        if result.status in (FetchStatus.SUCCESS, FetchStatus.SUCCESS_AFTER_BROWSER):
            context.set_html(result.html)
            cache.set(context.url, result.html, settings.SCRAPER_CACHE_TTL_SECONDS)
            return StepResult.success(message=f"html_fetched_via_{result.layer_used}")

        # Produto definitivamente indisponível (404/410/451) — retorna payload
        if result.availability is not None:
            context.set_html("")
            context.data["availability"] = result.availability
            context.data["last_status"] = result.last_status
            return StepResult.success(
                payload={
                    "name": None,
                    "current_price": None,
                    "url": context.url,
                    "source": context.source,
                    "availability": result.availability,
                    "last_status": result.last_status,
                },
                message="Disponibilidade inferida por código HTTP",
            )

        return StepResult.failure(message=result.error_code or "fetch_failed")
    

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
            context.data["no_domain_parser"] = True
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
