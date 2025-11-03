""" Utilitários de download HTTP usados pelo pipeline do scraper

O módulo isola toda a lógica responsável por obter o HTML de uma URL,
incluindo construção de headers, métricas e tratamento de erros. Esse
isolamento facilita testes e reutilização sem acoplar diretamente às
etapas do pipeline.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
import structlog

from shared.utils.logging_utils import sanitize_log_data

from market_scraper.core.config_scraper import settings
from market_scraper.utils import user_agents
from market_scraper.utils.headers import (
    REFERER_TEMPLATE_ERROR_EVENT,
    build_referer,
)
from market_scraper.utils.http_retry import (
    RetryableHTTPError,
    build_retrying_operation,
)
from market_scraper.utils.http_utils import ContentDecodeError, build_timeout, decode_http_body
from shared.metrics.metrics_scraper import (
    SCRAPER_HTTP_CLIENT_ERROR_TOTAL,
    SCRAPER_HTTP_DECODE_ERROR_TOTAL,
    SCRAPER_UA_ROTATION_TOTAL,
)


logger = structlog.get_logger("http_download")
_UA_STRATEGY_LABEL = "round_robin"

def extract_domain(url: str) -> str | None:
    """ Extrai domínio normalizado da URL para uso em métricas e logs """
    parsed = urlparse(url)
    return parsed.hostname

async def download_html(url: str, *, timeout: float) -> str:
    """ Baixa o HTML usando ``httpx`` aplicando limites rígidos de segurança """
    user_agent = user_agents.get_user_agent(url)
    domain = extract_domain(url)
    SCRAPER_UA_ROTATION_TOTAL.labels(
        strategy=_UA_STRATEGY_LABEL,
        domain=domain or "unknown",
    ).inc()

    referer = build_referer(
        url,
        logger=logger,
        event_name=REFERER_TEMPLATE_ERROR_EVENT,
    )
    headers = user_agents.compose_headers(user_agent, referer=referer)
    cookies = settings.get_default_cookies()

    #Ajustamos timeout global considerando possíveis overrides por domínio
    total_timeout = settings.resolve_domain_timeout(domain, timeout)

    #Usamos o helper centralizado para manter consistência na configuração de timeouts
    client_timeout = build_timeout(total_timeout)
    limits = httpx.Limits(
        max_connections=settings.SCRAPER_HTTP_MAX_CONNECTIONS,
        max_keepalive_connections=settings.SCRAPER_HTTP_MAX_KEEPALIVE,
    )

    async def _execute_request() -> httpx.Response:
        """ Encapsula a chamada HTTP para facilitar a aplicação de retries """
        async with httpx.AsyncClient(
            timeout=client_timeout,
            follow_redirects=settings.SCRAPER_HTTP_FOLLOW_REDIRECTS,
            limits=limits,
            max_redirects=settings.SCRAPER_HTTP_MAX_REDIRECTS,
        ) as client:
            return await client.get(
                url,
                headers=headers,
                cookies=cookies or None,
            )
        
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
    
    try:
        #Decodificamos o corpo respeitando Content-Encoding para evitar textos truncados
        return decode_http_body(response)
    except ContentDecodeError as exc:
        encoding = exc.encoding or (response.headers.get("Content-Encoding") or "unknown")
        domain_label = domain or "unknown"
        SCRAPER_HTTP_DECODE_ERROR_TOTAL.labels(
            domain=domain_label,
            encoding=encoding,
            reason=exc.reason,
        ).inc()
        logger.warning(
            "http_decode_error",
            domain=domain_label,
            url=sanitize_log_data(url),
            encoding=encoding,
            reason=exc.reason,
            error=sanitize_log_data(str(exc)),
        )
        raise ValueError("Falha ao decodificar corpo HTTP recebido") from exc
    
def _log_response_metadata(*, response: httpx.Response, url: str, domain: str | None, user_agent: str) -> None:
    """ Registra cabeçalhos principais da resposta para depuração detalhada """
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
    """ Registra contexto resumido de respostas 4xx para diagnóstico rápido """
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


__all__ = [
    "download_html",
    "extract_domain",
]
