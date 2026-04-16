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
from market_scraper.services.parser_runner import ParserCallable, run_parser_with_validation
from market_scraper.services.synergic_pipeline import (
    PipelineContext,
    PipelineStep,
    StepResult,
)
from market_scraper.services.availability_inference import infer_availability_from_http_status
from market_scraper.infra.adaptive_rate_limiter import adaptive_rate_limiter
from market_scraper.services.playwright_pool import (
    PlaywrightFetchError,
    PlaywrightPoolNotReadyError,
    PlaywrightTimeoutError,
    playwright_pool,
)
from market_scraper.services.response_classifier import ClassificationAction, ResponseClassifier
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
        
        #Decisão de cache é centralizada no contexto para manter coerência entre etapas
        if context.should_use_cache("html"):
            logger.info(
                "html_cache_check",
                url=context.url,
                domain=context.source,
                cache_name="html",
                force_refresh=context.force_refresh,
            )
            cached_html: str | None = cache.get(context.url)
            if cached_html is not None:
                context.set_html(cached_html)
                return StepResult.success(message="html_from_cache")

        async def _download() -> str:
            """ Encapsula o download respeitando timeout da etapa para coalescing """
            return await download_html(context.url, timeout=timeout_value)
        
        #O ``force_refresh`` entra na chave para evitar coalescer requisições com intenção divergente
        singleflight_key = f"{context.url}|force_refresh={context.force_refresh}"
        try:
            html, is_leader = await singleflight.coalesce_with_leader(singleflight_key, _download)
            if not is_leader:
                logger.info(
                    "html_fetch_coalesced",
                    url=context.url,
                    domain=context.source,
                    cache_key=singleflight_key,
                )
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
            if status_code is None:
                raise
            inference = infer_availability_from_http_status(status_code, context.source)
            context.data["availability_inferred"] = inference.availability
            context.data["last_status_inferred"] = inference.last_status
            logger.info(
                "http_status_availability_inferred",
                url=context.url,
                status_code=status_code,
                availability=inference.availability,
                last_status=inference.last_status,
                confidence=inference.confidence,
            )
            if inference.availability is False:
                logger.info(
                    "html_fetch_unavailable",
                    url=context.url,
                    status_code=status_code,
                    last_status=inference.last_status,
                )
                context.set_html("")
                context.data["availability"] = inference.availability
                context.data["last_status"] = inference.last_status
                context.data["availability_inferred"] = inference.availability
                context.data["last_status_inferred"] = inference.last_status
                return StepResult.success(
                    payload={
                        "name": None,
                        "current_price": None,
                        "url": context.url,
                        "source": context.source,
                        "availability": inference.availability,
                        "last_status": inference.last_status,
                    },
                    message="Disponibilidade inferida por código HTTP",
                )
            raise
        context.set_html(html)
        #Armazenamos o HTML recém obtido para acelerar futuras requisições
        cache.set(context.url, html, settings.SCRAPER_CACHE_TTL_SECONDS)
        logger.info(
            "html_cache_store",
            url=context.url,
            domain=context.source,
            cache_name="html",
            ttl_seconds=settings.SCRAPER_CACHE_TTL_SECONDS,
        )
        return StepResult.success(message="HTML baixado com sucesso")
    
class AntiBotDetectionStep(PipelineStep):
    """Detecta páginas de proteção anti-bot antes dos parsers

    Consome: ``context.html``
    Produz: ``context.data['anti_bot_detected']``, ``context.data['anti_bot_pattern']``

    Se detectar padrão conhecido, esvazia ``context.html`` para que as etapas
    de parsing subsequentes retornem ``empty`` imediatamente em vez de tentar
    extrair dados de uma página de challenge.
    """

    _PATTERNS: tuple[tuple[str, str], ...] = (
        ("suspicious-traffic-frontend", "mercadolivre_challenge"),
        ("challenges.cloudflare.com", "cloudflare_challenge"),
        ("__cf_chl", "cloudflare_challenge"),
        ("recaptcha/api.js", "captcha_challenge"),
        ("_pxcaptcha", "perimeterx_challenge"),
    )

    def __init__(self) -> None:
        super().__init__(name="anti_bot_detection")

    async def run(self, context: PipelineContext) -> StepResult:
        if not context.html:
            return StepResult.empty("HTML indisponível para detecção de anti-bot")

        html_lower = context.html.lower()
        for pattern, pattern_type in self._PATTERNS:
            if pattern.lower() in html_lower:
                context.data["anti_bot_detected"] = True
                context.data["anti_bot_pattern"] = pattern_type
                context.html = ""
                logger.warning(
                    "anti_bot_page_detected",
                    url=context.url,
                    domain=context.source,
                    pattern_type=pattern_type,
                )
                return StepResult.failure(message="anti_bot_page")

        return StepResult.empty("Nenhum padrão de anti-bot detectado")


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
    
class PlaywrightFetchStep(PipelineStep):
    """ Obtém HTML via Chromium headless (Camada 3 — fallback Playwright).

    Consome: ``context.url``
    Produz: ``context.html``

    Deve ser chamada apenas quando o classificador de resposta indica
    escalonamento para a Camada 3 (``ClassificationAction.SCALE``).
    O passo preserva o HTML já presente no contexto caso seja executado
    sem pool inicializado, tornando o fallback não-fatal.
    """

    def __init__(self, *, timeout: float | None = None) -> None:
        super().__init__(name="playwright_fetch", timeout=timeout)

    async def run(self, context: PipelineContext) -> StepResult:
        timeout_value = self.timeout if self.timeout is not None else context.default_step_timeout

        if not playwright_pool.is_ready:
            logger.warning(
                "playwright_pool_not_ready",
                url=context.url,
                domain=context.source,
            )
            return StepResult.failure(message="playwright_not_ready")

        try:
            html = await playwright_pool.fetch_html(context.url, timeout=timeout_value)
        except PlaywrightPoolNotReadyError:
            logger.warning(
                "playwright_pool_not_ready",
                url=context.url,
                domain=context.source,
            )
            return StepResult.failure(message="playwright_not_ready")
        except PlaywrightTimeoutError as exc:
            logger.warning(
                "playwright_fetch_timeout",
                url=context.url,
                domain=context.source,
                timeout=exc.timeout,
            )
            return StepResult.failure(message="playwright_timeout")
        except PlaywrightFetchError as exc:
            logger.warning(
                "playwright_fetch_error",
                url=context.url,
                domain=context.source,
                reason=exc.reason,
            )
            return StepResult.failure(message="playwright_fetch_error")

        context.set_html(html)
        context.data["layer_used"] = "playwright"
        logger.info(
            "playwright_fetch_success",
            url=context.url,
            domain=context.source,
            html_size=len(html),
        )
        return StepResult.success(message="html_fetched_via_playwright")


_response_classifier = ResponseClassifier()

class CascadeFetchStep(PipelineStep):
    """ Aquisição em cascata: curl_cffi (Camada 1) → Playwright (Camada 3).

    Consome: ``context.url``, ``context.source``
    Produz: ``context.html``, ``context.data['layer_used']``,
            ``context.data['classification_reason']``,
            ``context.data['fallback_taken']``

    Fluxo:
        1. Rate limiter pré-requisição (``adaptive_rate_limiter.should_allow``).
        2. Robots.txt check.
        3. Cache hit → retorno imediato.
        4. Camada 1 via ``download_html`` (curl_cffi) com singleflight.
        5. ResponseClassifier → SUCCESS termina aqui, SCALE → Camada 3.
        6. Camada 3 via ``playwright_pool.fetch_html`` quando disponível.
        7. Rate limiter pós-requisição (``adaptive_rate_limiter.update_history``).
    """

    def __init__(self, *, timeout: float | None = None) -> None:
        super().__init__(name="cascade_fetch", timeout=timeout)

    async def run(self, context: PipelineContext) -> StepResult:
        if context.html:
            return StepResult.success(message="HTML já presente no contexto")

        timeout_value = self.timeout if self.timeout is not None else context.default_step_timeout
        domain = context.source or extract_domain(context.url) or ""

        # ── 1. Rate limiter pre-check ─────────────────────────────────────
        allowed, suggested_layer = await adaptive_rate_limiter.should_allow(domain)
        if not allowed:
            logger.warning(
                "cascade_fetch_blocked_by_rate_limiter",
                url=context.url,
                domain=domain,
            )
            return StepResult.failure(message="rate_limiter_cooldown")

        # ── 2. Robots.txt ─────────────────────────────────────────────────
        if not await robots.is_allowed(context.url, timeout=timeout_value):
            return StepResult.failure(message="unsupported_by_robots")

        # ── 3. Cache ──────────────────────────────────────────────────────
        if context.should_use_cache("html"):
            cached_html: str | None = cache.get(context.url)
            if cached_html is not None:
                context.set_html(cached_html)
                return StepResult.success(message="html_from_cache")

        # ── 4. Camada 1 — curl_cffi ───────────────────────────────────────
        layer1_html: str | None = None
        layer1_exc: Exception | None = None
        layer1_status: int | None = None

        async def _download() -> str:
            return await download_html(context.url, timeout=timeout_value)

        singleflight_key = f"{context.url}|force_refresh={context.force_refresh}"
        try:
            layer1_html, is_leader = await singleflight.coalesce_with_leader(
                singleflight_key, _download
            )
            if not is_leader:
                logger.info("cascade_fetch_coalesced", url=context.url, domain=domain)
            layer1_status = 200
        except httpx.TooManyRedirects as exc:
            context.data["http_status"] = 422
            await adaptive_rate_limiter.update_history(
                domain, success=False, error_code="too_many_redirects"
            )
            return StepResult.failure(message="too_many_redirects")
        except (httpx.InvalidURL, httpx.UnsupportedProtocol) as exc:
            context.data["http_status"] = 422
            await adaptive_rate_limiter.update_history(
                domain, success=False, error_code="invalid_url"
            )
            return StepResult.failure(message="invalid_url")
        except httpx.HTTPStatusError as exc:
            layer1_status = exc.response.status_code if exc.response is not None else None
            context.data["http_status"] = layer1_status
            layer1_exc = exc
            if layer1_status is None:
                await adaptive_rate_limiter.update_history(
                    domain, success=False, error_code="unknown"
                )
                raise
            inference = infer_availability_from_http_status(layer1_status, domain)
            context.data["availability_inferred"] = inference.availability
            context.data["last_status_inferred"] = inference.last_status
            if inference.availability is False:
                context.set_html("")
                context.data["availability"] = inference.availability
                context.data["last_status"] = inference.last_status
                await adaptive_rate_limiter.update_history(
                    domain,
                    success=False,
                    error_code=str(layer1_status),
                    layer_used=1,
                )
                return StepResult.success(
                    payload={
                        "name": None,
                        "current_price": None,
                        "url": context.url,
                        "source": context.source,
                        "availability": inference.availability,
                        "last_status": inference.last_status,
                    },
                    message="Disponibilidade inferida por código HTTP",
                )
        except Exception as exc:
            layer1_exc = exc

        # ── 5. ResponseClassifier ─────────────────────────────────────────
        classification = _response_classifier.classify(
            http_status=layer1_status,
            html=layer1_html,
            error=layer1_exc,
        )
        context.data["classification_reason"] = classification.reason

        if classification.action == ClassificationAction.REJECT:
            await adaptive_rate_limiter.update_history(
                domain,
                success=False,
                error_code=str(layer1_status) if layer1_status else "rejected",
                layer_used=1,
            )
            logger.info(
                "cascade_fetch_rejected",
                url=context.url,
                domain=domain,
                reason=classification.reason,
            )
            #Retorna o erro HTTP original para preservar inferência de disponibilidade
            if layer1_exc is not None:
                raise layer1_exc
            return StepResult.failure(message=classification.reason)

        if classification.action == ClassificationAction.SUCCESS:
            #Camada 1 bem-sucedida
            context.set_html(layer1_html)  # type: ignore[arg-type]
            context.data["layer_used"] = "curl_cffi"
            context.data["fallback_taken"] = False
            context.data["http_status"] = context.data.get("http_status") or 200
            cache.set(context.url, layer1_html, settings.SCRAPER_CACHE_TTL_SECONDS)
            await adaptive_rate_limiter.update_history(
                domain, success=True, layer_used=1
            )
            logger.info(
                "cascade_fetch_layer1_success",
                url=context.url,
                domain=domain,
                html_size=len(layer1_html),  # type: ignore[arg-type]
            )
            return StepResult.success(message="html_fetched_via_curl_cffi")

        # ── 6. SCALE → Camada 3 — Playwright ─────────────────────────────
        # Fix #3: error_code reflete a razão real da classificação (ex: "anti_bot_page"),
        # não o status HTTP 200 que induziria o rate limiter a interpretar como sucesso.
        await adaptive_rate_limiter.update_history(
            domain,
            success=False,
            error_code=classification.reason,
            layer_used=1,
        )

        if not playwright_pool.is_ready:
            logger.warning(
                "cascade_fetch_playwright_not_ready",
                url=context.url,
                domain=domain,
                reason=classification.reason,
            )
            # Fix #1: anti_bot detectado sem fallback → 429 (retry possível quando Playwright
            # voltar). Qualquer outro motivo de SCALE sem fallback → 503 (pipeline degradado).
            if classification.reason == "anti_bot_page":
                return StepResult.failure(message="anti_bot_page")
            return StepResult.failure(message="pipeline_degraded")

        try:
            pw_html = await playwright_pool.fetch_html(context.url, timeout=timeout_value)
        except PlaywrightPoolNotReadyError:
            return StepResult.failure(message="playwright_not_ready")
        except PlaywrightTimeoutError as exc:
            logger.warning(
                "cascade_fetch_playwright_timeout",
                url=context.url,
                domain=domain,
                timeout=exc.timeout,
            )
            await adaptive_rate_limiter.update_history(
                domain, success=False, error_code="timeout", layer_used=3
            )
            return StepResult.failure(message="playwright_timeout")
        except PlaywrightFetchError as exc:
            logger.warning(
                "cascade_fetch_playwright_error",
                url=context.url,
                domain=domain,
                reason=exc.reason,
            )
            await adaptive_rate_limiter.update_history(
                domain, success=False, error_code="playwright_error", layer_used=3
            )
            return StepResult.failure(message="playwright_fetch_error")

        context.set_html(pw_html)
        context.data["layer_used"] = "playwright"
        context.data["fallback_taken"] = True
        context.data["http_status"] = context.data.get("http_status") or 200
        cache.set(context.url, pw_html, settings.SCRAPER_CACHE_TTL_SECONDS)
        await adaptive_rate_limiter.update_history(
            domain, success=True, layer_used=3
        )
        logger.info(
            "cascade_fetch_layer3_success",
            url=context.url,
            domain=domain,
            html_size=len(pw_html),
            l1_reason=classification.reason,
        )
        return StepResult.success(message="html_fetched_via_playwright")


def default_pipeline_steps() -> list[PipelineStep]:
    """ Retorna a sequência padrão de etapas do pipeline enxuto """
    steps: list[PipelineStep] = [
        CascadeFetchStep(),
        AntiBotDetectionStep(),
        JsonLdParserStep(),
        HtmlMetadataParserStep(),
        DomainSpecificParserStep(),
        GenericFallbackParserStep(),
    ]
    #Mantemos a ordem fixa para cumprir pipeline mínimo definido
    return steps

__all__ = [
    "FetchHTMLStep",
    "CascadeFetchStep",
    "PlaywrightFetchStep",
    "AntiBotDetectionStep",
    "JsonLdParserStep",
    "HtmlMetadataParserStep",
    "DomainSpecificParserStep",
    "GenericFallbackParserStep",
    "default_pipeline_steps",
]
