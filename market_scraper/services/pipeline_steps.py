""" Etapas básicas para o pipeline sequencial do MarketScraper

O módulo concentra a execução linear das etapas responsáveis por baixar
HTML e extrair o payload mínimo. Cada ``PipelineStep`` descreve quais
chaves do ``shared_context`` consome e quais atualiza, reduzindo efeitos
colaterais e facilitando testes.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping
from urllib.parse import urlparse

import httpx
import structlog

from shared.utils.logging_utils import sanitize_log_data

from market_scraper.core.config_scraper import settings
from market_scraper.parsers import (
    parse_generic_html,
    parse_with_beautifulsoup,
    parse_with_extruct,
)
from market_scraper.services.synergic_pipeline import PipelineContext, PipelineStep, StepResult
from market_scraper.utils import cache, robots, singleflight, user_agents
from market_scraper.utils.http_retry import(
    RetryableHTTPError,
    build_retrying_operation,
)
from market_scraper.utils.validator import DataQualityValidator
from shared.metrics.metrics_scraper import (
    SCRAPER_HTTP_CLIENT_ERROR_TOTAL,
    SCRAPER_UA_ROTATION_TOTAL,
)

_REFERER_TEMPLATE_ERROR_EVENT = "referer_template_error"
_UA_STRATEGY_LABEL = "round_robin"

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
    user_agent = user_agents.get_user_agent(url)
    domain = _extract_domain(url)
    SCRAPER_UA_ROTATION_TOTAL.labels(
        strategy=_UA_STRATEGY_LABEL,
        domain=domain or "unknown",
    ).inc()

    referer = _build_referer(url)
    headers = user_agents.compose_headers(user_agent, referer=referer)
    
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

    async def _execute_request() -> httpx.Response:
        async with httpx.AsyncClient(
            timeout=client_timeout,
            follow_redirects=True,
            limits=limits,
            max_redirects=settings.SCRAPER_HTTP_MAX_REDIRECTS,
        ) as client:
            return await client.get(url, headers=headers)
        
    wrapped_operation = build_retrying_operation(target="html", operation=_execute_request)

    try:
        response = await wrapped_operation()
    except RetryableHTTPError as exc:
        if exc.__cause__ is not None:
            raise exc.__cause__
        raise httpx.HTTPError("Falha ao baixar HTML após retries") from exc
    
    _log_response_metadata(
        response=response,
        url=url,
        domain=domain,
        user_agent=user_agent,
    )

    if 400 <= response.status_code < 500:
        _log_client_error(response=response, url=url, domain=domain, user_agent=user_agent)

    response.raise_for_status()

    content = response.content
    if len(content) > settings.SCRAPER_HTTP_MAX_CONTENT_LENGTH:
        raise ValueError("Resposta excedeu o tamanho máximo permitido")
    
    #Retornamos o texto decodificado após validar o tamanho bruto para evitar ataques de payload gigante
    return response.text

def _extract_domain(url: str) -> str | None:
    """ Normaliza o domínio da URL para métricas e logs """
    parsed = urlparse(url)
    return parsed.hostname

def _build_referer(url: str) -> str | None:
    """ Monta Referer opcional baseado no template configurado """
    template = settings.SCRAPER_HEADERS_REFERER_TEMPLATE
    if not template:
        return None
    
    domain = _extract_domain(url)
    if not domain:
        return None
    
    try:
        return template.format(domain=domain, url=url)
    except Exception:
        #Quando o template é inválido evitamos quebrar o download e omitimos o header
        logger.warning(
            _REFERER_TEMPLATE_ERROR_EVENT,
            template=sanitize_log_data(template),
            url=sanitize_log_data(url),
        )
        return None
    
def _log_response_metadata(*, response: httpx.Response, url: str, domain: str | None, user_agent: str) -> None:
    """ Registra cabeçalhos principais da resposta para depuração """
    logger.debug(
        "http_download_metadata",
        domain=(domain or "unknown"),
        url=sanitize_log_data(url),
        status_code=response.status_code,
        content_type=sanitize_log_data(response.headers.get("Content-Type")),
        content_encoding=sanitize_log_data(response.headers.get("Content-Encoding")),
        user_agent=sanitize_log_data(user_agent),
    )

def _log_client_error(*, response: httpx.Response, url: str, domain: str | None, user_agent: str) -> None:
    """ Registra contexto resumido de respostas 4xx para diagnóstico """

    domain_label = domain or "unknown"
    SCRAPER_HTTP_CLIENT_ERROR_TOTAL.labels(domain=domain_label, status=str(response.status_code)).inc()

    body_excerpt = None
    if settings.SCRAPER_LOG_4XX_BODY:
        raw_excerpt = response.content[: settings.SCRAPER_LOG_4XX_MAX_BYTES]
        encoding = response.encoding or "utf-8"
        decoded_excerpt = raw_excerpt.decode(encoding, errors="replace")
        body_excerpt = sanitize_log_data(decoded_excerpt)

    logger.warning(
        "http_client_error",
        domain=domain_label,
        url=sanitize_log_data(url),
        status_code=response.status_code,
        body_excerpt=body_excerpt,
        user_agent=sanitize_log_data(user_agent),
    )

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
            #Ajuste de código de falha alinhado com documentação pública do serviço
            return StepResult.failure(message="unsupported_by_robots")
        
        #A checagem de cache evita roud-trips desnecessários mantendo métricas de hit/miss atualizadas
        cached_html: str | None = cache.get(context.url)
        if cached_html is not None:
            context.set_html(cached_html)
            return StepResult.success(message="html_from_cache")

        async def _download() -> str:
            """ Encapsula o download respeitando timeout da etapa para coalescing """
            return await download_html(context.url, timeout=timeout_value)
        
        #O singleflight garante que somente um download efetivo ocorra por URL
        html = await singleflight.coalesce(context.url, _download)
        context.set_html(html)
        #Armazenamos o HTML recém obtido para acelerar futuras requisições
        cache.set(context.url, html, settings.SCRAPER_CACHE_TTL_SECONDS)
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
    
def default_pipeline_steps() -> list[PipelineStep]:
    """ Retorna a sequência padrão de etapas do pipeline enxuto """
    steps: list[PipelineStep] = [
        FetchHTMLStep(),
        JsonLdParserStep(),
        HtmlMetadataParserStep(),
        GenericFallbackParserStep(),
    ]
    #Mantemos a ordem fixa para cumprir pipeline mínimo definido
    return steps

__all__ = [
    "FetchHTMLStep",
    "JsonLdParserStep",
    "HtmlMetadataParserStep",
    "GenericFallbackParserStep",
    "default_pipeline_steps",
    "download_html",
]
