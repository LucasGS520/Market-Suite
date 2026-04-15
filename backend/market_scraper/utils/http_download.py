""" Utilitários de download HTTP usados pelo pipeline do scraper

O módulo isola toda a lógica responsável por obter o HTML de uma URL.
A Camada 1 usa ``curl_cffi`` com TLS impersonation Chrome para contornar
bloqueios de fingerprint sem depender de proxy externo.

Todas as exceções são mapeadas para equivalentes ``httpx`` para preservar
o contrato com ``FetchHTMLStep`` sem nenhuma quebra de interface.
"""

from __future__ import annotations

import enum
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
from market_scraper.utils.http_utils import parse_retry_after


logger = structlog.get_logger("http_download")

# ─────────────────────────────────────────────────────────────────────────────
# Constantes internas — libcurl error codes relevantes
# ─────────────────────────────────────────────────────────────────────────────

_CURL_UNSUPPORTED_PROTO = 1   # CURLE_UNSUPPORTED_PROTOCOL
_CURL_URL_MALFORMAT = 3       # CURLE_URL_MALFORMAT
_CURL_CONNECT_FAIL = 7        # CURLE_COULDNT_CONNECT
_CURL_TIMEOUT = 28            # CURLE_OPERATION_TIMEDOUT
_CURL_TOO_MANY_REDIRECTS = 47 # CURLE_TOO_MANY_REDIRECTS

#Tamanho mínimo esperado para um HTML útil (5 KB)
_MIN_HTML_SIZE_BYTES = 5 * 1024


# ─────────────────────────────────────────────────────────────────────────────
# Classificação pública de erros da Camada 1
# ─────────────────────────────────────────────────────────────────────────────

class CurlcffiErrorType(enum.Enum):
    """ Classifica erros da Camada 1 para decisões de escalonamento futuras."""
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    TOO_MANY_REQUESTS = "too_many_requests"
    ACCESS_DENIED = "access_denied"
    NOT_FOUND = "not_found"
    TOO_MANY_REDIRECTS = "too_many_redirects"
    INVALID_URL = "invalid_url"
    UNSUPPORTED_PROTOCOL = "unsupported_protocol"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Cliente HTTP de Camada 1
# ─────────────────────────────────────────────────────────────────────────────

class CurlffiHTTPClient:
    """ Realiza downloads com TLS impersonation Chrome via ``curl_cffi``.

    Cada chamada a ``fetch_html`` cria uma nova ``AsyncSession`` para
    garantir isolamento entre requisições concorrentes. Exceções internas
    do curl são convertidas para equivalentes ``httpx`` de forma que
    ``FetchHTMLStep`` não perceba a troca de cliente HTTP.
    """

    _CHROME_IMPERSONATION = "chrome124"

    async def fetch_html(self, url: str, *, timeout: float) -> str:
        """ Baixa o HTML aplicando TLS impersonation Chrome (Camada 1).

        Args:
            url: URL completa do produto a raspar.
            timeout: Tempo máximo total da requisição em segundos.

        Returns:
            String com o HTML completo da página.

        Raises:
            httpx.ReadTimeout: timeout durante o download.
            httpx.ConnectError: falha de conexão (DNS, TCP).
            httpx.TooManyRedirects: redirecionamentos em excesso.
            httpx.InvalidURL: URL malformada.
            httpx.UnsupportedProtocol: protocolo não suportado.
            httpx.HTTPStatusError: resposta 4xx ou 5xx.
            ValueError: corpo excede tamanho máximo ou falha de decode.
        """
        try:
            from curl_cffi.requests import AsyncSession, RequestsError
        except ImportError as exc:
            raise RuntimeError(
                "curl_cffi não instalado; execute: pip install curl_cffi"
            ) from exc

        domain = extract_domain(url)
        user_agent = user_agents.get_user_agent(url)
        referer = build_referer(url, logger=logger, event_name=REFERER_TEMPLATE_ERROR_EVENT)
        headers = self._compose_headers(user_agent, referer=referer)
        cookies = settings.get_default_cookies()
        total_timeout = settings.resolve_domain_timeout(domain, timeout)

        try:
            async with AsyncSession(impersonate=self._CHROME_IMPERSONATION) as session:
                response = await session.get(
                    url,
                    headers=headers,
                    cookies=cookies or None,
                    timeout=total_timeout,
                    allow_redirects=settings.SCRAPER_HTTP_FOLLOW_REDIRECTS,
                    max_redirects=settings.SCRAPER_HTTP_MAX_REDIRECTS,
                )
        except RequestsError as exc:
            raise self._map_curl_error(exc, url=url) from exc

        self._log_response_metadata(
            url=url,
            domain=domain,
            user_agent=user_agent,
            status_code=response.status_code,
            content_type=response.headers.get("Content-Type"),
            content_encoding=response.headers.get("Content-Encoding"),
        )

        if response.status_code >= 400:
            if 400 <= response.status_code < 500:
                self._log_client_error(
                    url=url,
                    domain=domain,
                    user_agent=user_agent,
                    status_code=response.status_code,
                    content=response.content,
                )
            self._raise_http_status_error(url=url, status_code=response.status_code)

        content = response.content
        if len(content) > settings.SCRAPER_HTTP_MAX_CONTENT_LENGTH:
            raise ValueError("Resposta excedeu o tamanho máximo permitido")

        try:
            html = response.text
        except Exception as exc:
            logger.warning(
                "curl_cffi_decode_error",
                domain=domain or "unknown",
                url=sanitize_log_data(url),
                error=sanitize_log_data(str(exc)),
            )
            raise ValueError("Falha ao decodificar corpo HTTP recebido") from exc

        logger.debug(
            "curl_cffi_fetch_success",
            domain=domain or "unknown",
            url=sanitize_log_data(url),
            status_code=response.status_code,
            response_size=len(content),
            curl_impersonation_used=self._CHROME_IMPERSONATION,
        )

        return html

    # ── Composição de headers ──────────────────────────────────────────────

    def _compose_headers(self, user_agent: str, *, referer: str | None) -> dict[str, str]:
        """ Monta headers simulando Chrome com Accept-Language pt-BR."""
        base = user_agents.compose_headers(user_agent, referer=referer)
        # curl_cffi gerencia Accept-Encoding automaticamente via libcurl,
        # mas declaramos explicitamente para maior fidelidade ao Chrome.
        base.setdefault("Accept-Encoding", settings.SCRAPER_HEADERS_ACCEPT_ENCODING)
        return base

    # ── Mapeamento de erros curl → httpx ──────────────────────────────────

    def _map_curl_error(self, exc: Exception, *, url: str) -> Exception:
        """ Converte ``RequestsError`` para equivalente ``httpx`` preservando o contrato."""
        raw_code = getattr(exc, "code", None)
        #curl_cffi pode expor code como enum ou int dependendo da versão
        error_code: int | None = raw_code.value if hasattr(raw_code, "value") else raw_code
        msg = str(exc)

        if error_code == _CURL_TIMEOUT:
            logger.warning(
                "curl_cffi_timeout",
                url=sanitize_log_data(url),
                curl_error_code=error_code,
            )
            return httpx.ReadTimeout(msg, request=httpx.Request("GET", url))

        if error_code == _CURL_TOO_MANY_REDIRECTS:
            logger.warning("curl_cffi_too_many_redirects", url=sanitize_log_data(url))
            return httpx.TooManyRedirects(msg, request=httpx.Request("GET", url))

        if error_code == _CURL_URL_MALFORMAT:
            logger.warning("curl_cffi_invalid_url", url=sanitize_log_data(url))
            return httpx.InvalidURL(msg)

        if error_code == _CURL_UNSUPPORTED_PROTO:
            return httpx.UnsupportedProtocol(msg, request=httpx.Request("GET", url))

        logger.warning(
            "curl_cffi_connection_error",
            url=sanitize_log_data(url),
            curl_error_code=error_code,
            error=sanitize_log_data(msg),
        )
        return httpx.ConnectError(msg, request=httpx.Request("GET", url))

    def _raise_http_status_error(self, *, url: str, status_code: int) -> None:
        """Levanta ``httpx.HTTPStatusError`` com status_code correto para o handler."""
        fake_req = httpx.Request("GET", url)
        fake_resp = httpx.Response(status_code, request=fake_req)
        raise httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=fake_req,
            response=fake_resp,
        )

    # ── Logging ───────────────────────────────────────────────────────────

    def _log_response_metadata(
        self,
        *,
        url: str,
        domain: str | None,
        user_agent: str,
        status_code: int,
        content_type: str | None,
        content_encoding: str | None,
    ) -> None:
        logger.debug(
            "http_download_metadata",
            domain=domain or "unknown",
            url=sanitize_log_data(url),
            status_code=status_code,
            content_type=sanitize_log_data(content_type),
            content_encoding=sanitize_log_data(content_encoding),
            user_agent=sanitize_log_data(user_agent),
            curl_impersonation_used=self._CHROME_IMPERSONATION,
        )

    def _log_client_error(
        self,
        *,
        url: str,
        domain: str | None,
        user_agent: str,
        status_code: int,
        content: bytes,
    ) -> None:
        domain_label = domain or "unknown"
        body_excerpt = None
        if settings.SCRAPER_LOG_4XX_BODY:
            raw = content[: settings.SCRAPER_LOG_4XX_MAX_BYTES]
            body_excerpt = sanitize_log_data(raw.decode("utf-8", errors="replace"))
        logger.warning(
            "http_client_error",
            domain=domain_label,
            url=sanitize_log_data(url),
            status_code=status_code,
            body_excerpt=body_excerpt,
            user_agent=sanitize_log_data(user_agent),
        )


# ─────────────────────────────────────────────────────────────────────────────
# API pública — contrato inalterado para FetchHTMLStep
# ─────────────────────────────────────────────────────────────────────────────

def extract_domain(url: str) -> str | None:
    """ Extrai domínio normalizado da URL para uso em logs."""
    parsed = urlparse(url)
    return parsed.hostname

async def download_html(url: str, *, timeout: float) -> str:
    """ Baixa o HTML usando ``curl_cffi`` com TLS impersonation (Camada 1).

    Interface idêntica à versão anterior com ``httpx``:
    retorna string HTML ou levanta exceções httpx-compatíveis.
    """
    client = CurlffiHTTPClient()
    return await client.fetch_html(url, timeout=timeout)


__all__ = [
    "CurlcffiErrorType",
    "CurlffiHTTPClient",
    "download_html",
    "extract_domain",
]
