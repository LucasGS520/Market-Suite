""" Cliente resiliente para integração com ``market_scraper`` """

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from threading import Lock
from typing import Any, Mapping
from urllib.parse import urlparse
from uuid import UUID

import httpx
import structlog

from pydantic import ValidationError

from backend.shared.schemas.shared_schemas_scraper import ParserRequest, ParserResponse
from shared.utils.redis_client import get_redis_client

from market_alert.core.config_alert import settings
from market_alert.utils.circuit_breaker import CircuitBreaker
from market_alert.utils.rate_limiter import RateLimiter


logger = structlog.get_logger(__name__)

ALLOWED_SCRAPER_FIELDS = {
    "currency",
    "availability",
    "thumbnail",
    "free_shipping",
    "seller",
    "seller_rating",
    "old_price",
    "etag",
    "last_modified",
}

class ScraperClientError(Exception):
    """ Representa falhas de comunicação ou regras de proteção do cliente """
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after

@dataclass(slots=True)
class ScraperFetchResult:
    """ Contém dados normalizados da resposta do serviço de scraping """
    status_code: int
    payload: ParserResponse | None
    headers: Mapping[str, str]
    error_code: str | None = None
    retry_after: int | None = None

    def dump_payload(self) -> dict[str, Any] | None:
        """ Retorna o corpo em formato ``dict`` para compatibilidade """
        return self.payload.model_dump() if self.payload else None

def _build_timeout() -> httpx.Timeout:
    """ Configura timeout composto respeitando limites do serviço """
    return httpx.Timeout(
        timeout=settings.SCRAPER_TOTAL_TIMEOUT,
        connect=settings.SCRAPER_CONNECT_TIMEOUT,
        read=settings.SCRAPER_READ_TIMEOUT,
    )

def _build_async_client(
    base_url: str,
    headers: dict[str, str] | None,
) -> httpx.AsyncClient:
    """ Cria ``AsyncClient`` com limites de conexão configurados """
    limits = httpx.Limits(
        max_connections=getattr(settings, "SCRAPER_HTTP_MAX_CONNECTIONS", 100),
        max_keepalive_connections=getattr(settings, "SCRAPER_HTTP_MAX_KEEPALIVE", 20),
        keepalive_expiry=getattr(settings, "SCRAPER_HTTP_KEEPALIVE_EXPIRY", 30.0),
    )
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=_build_timeout(),
        headers=headers,
        limits=limits,
    )

_CLIENT_POOL: dict[str, tuple[httpx.AsyncClient, int]] = {}
_POOL_LOCK = Lock()

def _sanitize_parser_response(response: ParserResponse) -> ParserResponse:
    """Reduz o payload retornado pelo scraper apenas ao que é essencial.

    O scraper pode enviar campos auxiliares diversos no atributo ``payload``.
    Para manter previsibilidade e evitar ruído no frontend, filtramos os
    metadados aceitando somente chaves permitidas, priorizando preço,
    disponibilidade e moeda.
    """
    extras = dict(response.payload or {})
    filtered_payload = {k: v for k, v in extras.items() if k in ALLOWED_SCRAPER_FIELDS}
    return response.model_copy(update={"payload": filtered_payload or None})

def _acquire_http_client(
    base_url: str,
    headers: dict[str, str] | None,
) -> tuple[httpx.AsyncClient, str]:
    """ Retorna cliente compartilhado incrementando o contador de uso 
    
    Cabeçalhos adicionais são aplicados apenas na criação inicial para
    impedir que uma chamada altere o estado global usado por outras
    requisições reutilizadas.
    """
    key = base_url
    with _POOL_LOCK:
        entry = _CLIENT_POOL.get(key)
        if entry:
            client, refcount = entry
            _CLIENT_POOL[key] = (client, refcount + 1)
            return client, key
        
        client = _build_async_client(base_url, headers)
        _CLIENT_POOL[key] = (client, 1)
        return client, key
    
async def _release_http_client(key: str, client: httpx.AsyncClient) -> None:
    """ Diminui contador de uso e encerra cliente quanado não há consumidores """
    close_client = False
    with _POOL_LOCK:
        entry = _CLIENT_POOL.get(key)
        if not entry:
            close_client = True
        else:
            pooled_client, refcount = entry
            if pooled_client is not client or refcount <= 1:
                close_client = True
                _CLIENT_POOL.pop(key, None)
            else:
                _CLIENT_POOL[key] = (pooled_client, refcount - 1)

    if close_client:
        await client.aclose()

rate_limiter = RateLimiter(
    get_redis_client,
    max_requests=settings.SCRAPER_HOST_RATE_LIMIT,
    window_seconds=settings.SCRAPER_HOST_RATE_WINDOW_SECONDS,
)

circuit_breaker = CircuitBreaker(
    get_redis_client,
    failure_threshold=settings.SCRAPER_CIRCUIT_FAILURE_THRESHOLD,
    failure_window=settings.SCRAPER_CIRCUIT_WINDOW_SECONDS,
    cooldown_seconds=settings.SCRAPER_CIRCUIT_COOLDOWN_SECONDS,
)

@dataclass
class ScraperClient:
    """ Cliente HTTP assíncrono com retries, rate limit e circuit breaker """
    base_url: str = settings.SCRAPER_SERVICE_URL
    client: httpx.AsyncClient = field(init=False)
    _client_key: str = field(init=False)
    _closed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """ Inicializa o ``AsyncClient`` com parâmetros de timeout configurados """
        user_agent = getattr(settings, "HTTP_USER_AGENT", None)
        default_headers = {"User-Agent": user_agent} if user_agent else None
        self.client, self._client_key = _acquire_http_client(
            self.base_url, default_headers
        )

    async def fetch(
        self,
        *,
        url: str,
        monitored_id: str | None = None,
        etag: str | None = None,
        last_modified: datetime | None = None,
        force_refresh: bool = False,
        product_type: str | None = None,
        user_id: UUID | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ScraperFetchResult:
        """ Executa POST no ``/scraper/parse`` com proteção contra sobrecarga """
        parsed = urlparse(url)
        host = parsed.netloc or "unknown"

        if circuit_breaker.is_open(host):
            raise ScraperClientError(
                "Circuito aberto para host solicitado",
                status_code=503,
            )
        
        if not rate_limiter.allow(host):
            raise ScraperClientError(
                "Limite de requisições para host excedido",
                status_code=429,
            )
        
        headers: dict[str, str] = {}
        if not force_refresh and etag:
            headers["If-None-Match"] = etag
        if not force_refresh and last_modified:
            headers["If-Modified-Since"] = format_datetime(last_modified, usegmt=True)

        if settings.SCRAPER_SERVICE_AUTH_HEADER and settings.SCRAPER_SERVICE_AUTH_TOKEN:
            headers[settings.SCRAPER_SERVICE_AUTH_HEADER] = settings.SCRAPER_SERVICE_AUTH_TOKEN

        request_model = ParserRequest(
            url=url,
            product_type=product_type or "monitored",
            user_id=user_id,
        )
        request_payload = request_model.model_dump(exclude_none=True)
        if "url" in request_payload:
            request_payload["url"] = str(request_payload["url"])
        if "user_id" in request_payload and request_payload["user_id"] is not None:
            request_payload["user_id"] = str(request_payload["user_id"])

        extra_metadata: dict[str, Any] = dict(metadata or {})
        if monitored_id:
            extra_metadata.setdefault("monitored_id", monitored_id)
        if force_refresh:
            extra_metadata.setdefault("force_refresh", force_refresh)
        if extra_metadata:
            request_payload["metadata"] = extra_metadata

        attempt = 0
        backoff = settings.SCRAPER_RETRY_BACKOFF_MIN

        while True:
            attempt += 1
            try:
                response = await self.client.post(
                    "/scraper/parse",
                    json=request_payload,
                    headers=headers or None,
                )
            except httpx.TimeoutException as exc:
                circuit_breaker.record_failure(host)
                if attempt >= settings.SCRAPER_RETRY_ATTEMPTS:
                    raise ScraperClientError(
                        "Tempo limite ao consultar o serviço de scraping",
                        status_code=504,
                    ) from exc
                await asyncio.sleep(self._compute_backoff(backoff, attempt))
                continue
            except httpx.RequestError as exc:
                circuit_breaker.record_failure(host)
                raise ScraperClientError(
                    f"Falha de transporte ao consultar o scraper: {exc}",
                    status_code=503,
                ) from exc

            status_code = response.status_code

            if status_code == 200:
                try:
                    parsed_payload = ParserResponse.model_validate(response.json())
                    parsed_payload = _sanitize_parser_response(parsed_payload)
                except ValidationError as exc:
                    circuit_breaker.record_failure(host)
                    raise ScraperClientError(
                        "Resposta inválida recebida do serviço de scraping",
                        status_code=500,
                    ) from exc
                circuit_breaker.record_success(host)
                return ScraperFetchResult(
                    status_code=status_code,
                    payload=parsed_payload,
                    headers=response.headers,
                    error_code="not_modified",
                )

            if status_code == 304:
                circuit_breaker.record_success(host)
                return ScraperFetchResult(
                    status_code=status_code,
                    payload=None,
                    headers=response.headers,
                )

            if status_code == 422:
                body = response.json()
                error_code = body.get("error_code")
                circuit_breaker.record_success(host)
                return ScraperFetchResult(
                    status_code=status_code,
                    payload=None,
                    headers=response.headers,
                    error_code=error_code,
                )

            if status_code in {429}:
                circuit_breaker.record_failure(host)
                retry_after = self._extract_retry_after(response)
                if attempt >= settings.SCRAPER_RETRY_ATTEMPTS:
                    raise ScraperClientError(
                        "Serviço de scraping respondeu com 429",
                        status_code=status_code,
                        retry_after=retry_after,
                    )
                await asyncio.sleep(self._calculate_retry_delay(backoff, attempt, retry_after))
                continue

            if 500 <= status_code < 600:
                circuit_breaker.record_failure(host)
                if attempt >= settings.SCRAPER_RETRY_ATTEMPTS:
                    raise ScraperClientError(
                        "Erro 5xx ao consultar o serviço de scraping",
                        status_code=status_code,
                    )
                await asyncio.sleep(self._compute_backoff(backoff, attempt))
                continue

            circuit_breaker.record_failure(host)
            raise ScraperClientError(
                f"Resposta inesperada do scraper: {status_code}",
                status_code=status_code,
            )

    async def aclose(self) -> None:
        """ Encerra a sessão HTTP assíncrona para liberar recursos """
        if self._closed:
            return
        self._closed = True
        await _release_http_client(self._client_key, self.client)

    async def __aenter__(self) -> "ScraperClient":
        """ Permite usar ``ScraperClient`` como contexto assíncrono """
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """ Garante que o cliente seja fechado ao sair do contexto """
        await self.aclose()

    async def parse(
        self,
        *,
        url: str,
        product_type: str | None = None,
        monitored_id: str | None = None,
        user_id: UUID | None = None,
        metadata: Mapping[str, Any] | None = None,
        etag: str | None = None,
        last_modified: datetime | None = None,
        force_refresh: bool = False,
    ) -> ParserResponse | None:
        """ Executa ``fetch`` reaproveitando cabeçalhos condicionais e força atualização """
        result = await self.fetch(
            url=url,
            monitored_id=monitored_id,
            etag=etag,
            last_modified=last_modified,
            force_refresh=force_refresh,
            product_type=product_type,
            user_id=user_id,
            metadata=metadata,
        )

        if result.status_code == 200 and result.payload:
            return result.payload
        
        if result.status_code == 304:
            return None
        
        if result.error_code:
            raise ScraperClientError(
                f"Erro retornado pelo scraper: {result.error_code}",
                status_code=result.status_code,
            )
        
        raise ScraperClientError(
            "Resposta sem payload válida retornada pelo scraper",
            status_code=result.status_code,
        )

    @staticmethod
    def _compute_backoff(base: float, attempt: int) -> float:
        """ Calcula backoff exponencial com jitter aleatório """
        exp = min(settings.SCRAPER_RETRY_BACKOFF_MAX, base * (2 ** (attempt - 1)))
        jitter = random.uniform(0, base)
        return exp + jitter
    
    @staticmethod
    def _calculate_retry_delay(base: float, attempt: int, retry_after: int | None) -> float:
        """ Seleciona entre ``Retry-After`` e backoff exponencial """
        if retry_after is not None:
            return float(retry_after)
        return ScraperClient._compute_backoff(base, attempt)
    
    @staticmethod
    def _extract_retry_after(response: httpx.Response) -> int | None:
        """ Extrai valor numérico do cabeçalho ``Retry-After`` quando presente """
        header = response.headers.get("Retry-After")
        if header is None:
            return None
        header = header.strip()
        if not header:
            return None
        try:
            return int(header)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(header)
            except (TypeError, ValueError):
                logger.warning("invalid_retry_after_header", value=header)
                return None
            
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            else:
                retry_at = retry_at.astimezone(timezone.utc)

            now = datetime.now(timezone.utc)
            delay_seconds = (retry_at - now).total_seconds()
            return max(0, int(delay_seconds))
        