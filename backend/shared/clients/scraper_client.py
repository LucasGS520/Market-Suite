""" Cliente resiliente e síncrono para integração com ``market_scraper``.

O objetivo é evitar dependências de event loop dentro das tasks Celery,
criando um cliente de vida curta por execução e encerrando-o sempre ao
final da chamada. Dessa forma o worker permanece previsível e livre de
erros como "event loop is closed".
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from typing import Any, Mapping
from urllib.parse import urlparse
from uuid import UUID

import httpx
import structlog

from pydantic import ValidationError

from shared.schemas import ParserRequest, ParserResponse
from shared.utils import normalize_scraper_response
from shared.utils.redis_client import get_redis_operational

from market_alert.core.config_alert import settings
from market_alert.infraestructure.resilience.circuit_breaker import CircuitBreaker
from market_alert.infraestructure.resilience.rate_limiter import RateLimiter


logger = structlog.get_logger(__name__)

ALLOWED_SCRAPER_FIELDS = {
    "currency",
    "availability",
    "last_status",
    "thumbnail",
    "free_shipping",
    "seller",
    "seller_rating",
    "old_price",
    "etag",
    "last_modified",
    "not_modified",
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
    """ Configura timeout composto garantindo valores coerentes com o scraper.

    O timeout total precisa ser compatível com os limites de conexão e leitura
    definidos por configuração para evitar ``ValueError`` do httpx em cenários
    onde o total seja inferior à soma de ``connect`` e ``read``. Ajustamos o
    total para o mínimo coerente, privilegiando estabilidade quando variáveis
    de ambiente estiverem descalibradas
    """
    minimal_total = settings.SCRAPER_CONNECT_TIMEOUT + settings.SCRAPER_READ_TIMEOUT
    total = max(settings.SCRAPER_TOTAL_TIMEOUT, minimal_total)
    return httpx.Timeout(
        timeout=total,
        connect=settings.SCRAPER_CONNECT_TIMEOUT,
        read=settings.SCRAPER_READ_TIMEOUT,
    )

def _build_sync_client(
    base_url: str,
    headers: dict[str, str] | None,
) -> httpx.Client:
    """ Cria ``Client`` síncrono com limites de conexão configurados """
    limits = httpx.Limits(
        max_connections=getattr(settings, "SCRAPER_HTTP_MAX_CONNECTIONS", 100),
        max_keepalive_connections=getattr(settings, "SCRAPER_HTTP_MAX_KEEPALIVE", 20),
        keepalive_expiry=getattr(settings, "SCRAPER_HTTP_KEEPALIVE_EXPIRY", 30.0),
    )
    return httpx.Client(
        base_url=base_url,
        timeout=_build_timeout(),
        headers=headers,
        limits=limits,
    )

def _sanitize_parser_response(response: ParserResponse) -> ParserResponse:
    """Reduz o payload retornado pelo scraper apenas ao que é essencial.

    O scraper pode enviar campos auxiliares diversos no atributo ``payload``.
    Para manter previsibilidade e evitar ruído no frontend, filtramos os
    metadados aceitando somente chaves permitidas, priorizando preço,
    disponibilidade e moeda.
    """
    extras = dict(response.payload or {})
    filtered_payload = {k: v for k, v in extras.items() if k in ALLOWED_SCRAPER_FIELDS}
    sanitized = response.model_copy(update={"payload": filtered_payload or None})
    removed_fields = sorted(set(extras.keys()) - set(filtered_payload.keys()))
    price_filtered = response.current_price is not None and sanitized.current_price is None
    if removed_fields or price_filtered:
        reason = "price_filtered" if price_filtered else "payload_filtered"
        logger.info(
            "scraper_response_sanitized",
            removed_fields=removed_fields,
            last_status=sanitized.last_status,
            price_filtered=price_filtered,
        )
    return sanitized

#Definição global para reaproveitar o bucket entre instâncias e evitar picos
rate_limiter = RateLimiter(
    get_redis_operational,
    max_requests=settings.SCRAPER_HOST_RATE_LIMIT,
    window_seconds=settings.SCRAPER_HOST_RATE_WINDOW_SECONDS,
)

circuit_breaker = CircuitBreaker(
    get_redis_operational,
    failure_threshold=settings.SCRAPER_CIRCUIT_FAILURE_THRESHOLD,
    failure_window=settings.SCRAPER_CIRCUIT_WINDOW_SECONDS,
    cooldown_seconds=settings.SCRAPER_CIRCUIT_COOLDOWN_SECONDS,
)

@dataclass
class ScraperClient:
    """ Cliente HTTP síncrono com retries, rate limit e circuit breaker """
    base_url: str = settings.SCRAPER_SERVICE_URL
    client: httpx.Client = field(init=False)
    _closed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """ Inicializa o ``Client`` com parâmetros de timeout configurados """
        user_agent = getattr(settings, "HTTP_USER_AGENT", None)
        default_headers = {"User-Agent": user_agent} if user_agent else None
        self.client = _build_sync_client(self.base_url, default_headers)

    def fetch(
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
            if not rate_limiter.allow(host):
                retry_count = self._register_host_retry_window(host)
                if self._host_retry_exhausted(retry_count):
                    raise ScraperClientError(
                        "Limite de tentativas por host excedido",
                        status_code=429,
                        retry_after=settings.SCRAPER_HOST_RETRY_WINDOW_SECONDS,
                    )
                if attempt >= settings.SCRAPER_RETRY_ATTEMPTS:
                    raise ScraperClientError(
                        "Limite de requisições para host excedido",
                        status_code=429,
                    )
                time.sleep(self._calculate_retry_delay(backoff, attempt, None))
                continue
            try:
                response = self.client.post(
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
                time.sleep(self._compute_backoff(backoff, attempt))
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
                    raw_body = response.json()
                except ValueError as exc:
                    circuit_breaker.record_failure(host)
                    raise ScraperClientError(
                        "Corpo JSON inválido retornado pelo serviço de scraping",
                        status_code=500,
                    ) from exc

                try:
                    parsed_payload = normalize_scraper_response(
                        raw_body,
                        source="client",
                        request_id=(extra_metadata.get("request_id") if extra_metadata else None),
                        correlation_id=(extra_metadata.get("correlation_id") if extra_metadata else None),
                    )
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
                )

            if status_code == 304:
                circuit_breaker.record_success(host)
                return ScraperFetchResult(
                    status_code=status_code,
                    payload=None,
                    headers=response.headers,
                )

            if status_code == 422:
                try:
                    body = response.json()
                except ValueError as exc:
                    circuit_breaker.record_failure(host)
                    raise ScraperClientError(
                        "Corpo JSON inválido retornado pelo serviço de scraping",
                        status_code=500,
                    ) from exc
                error_code = body.get("error_code")
                circuit_breaker.record_success(host)
                return ScraperFetchResult(
                    status_code=status_code,
                    payload=None,
                    headers=response.headers,
                    error_code=error_code,
                )
            
            if status_code in {400, 403}:
                try:
                    body = response.json()
                except ValueError as exc:
                    circuit_breaker.record_failure(host)
                    raise ScraperClientError(
                        "Corpo JSON inválido retornado pelo serviço de scraping",
                        status_code=500,
                    ) from exc
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
                retry_count = self._register_host_retry_window(host)
                if self._host_retry_exhausted(retry_count):
                    raise ScraperClientError(
                        "Limite de tentativas por host excedido",
                        status_code=status_code,
                        retry_after=retry_after,
                    )
                if attempt >= settings.SCRAPER_RETRY_ATTEMPTS:
                    raise ScraperClientError(
                        "Serviço de scraping respondeu com 429",
                        status_code=status_code,
                        retry_after=retry_after,
                    )
                time.sleep(self._calculate_retry_delay(backoff, attempt, retry_after))
                continue

            if 500 <= status_code < 600:
                circuit_breaker.record_failure(host)
                if attempt >= settings.SCRAPER_RETRY_ATTEMPTS:
                    raise ScraperClientError(
                        "Erro 5xx ao consultar o serviço de scraping",
                        status_code=status_code,
                    )
                time.sleep(self._compute_backoff(backoff, attempt))
                continue

            circuit_breaker.record_failure(host)
            raise ScraperClientError(
                f"Resposta inesperada do scraper: {status_code}",
                status_code=status_code,
            )

    def close(self) -> None:
        """ Encerra a sessão HTTP síncrona para liberar recursos """
        if self._closed:
            return
        self._closed = True
        self.client.close()

    def __enter__(self) -> "ScraperClient":
        """ Permite usar ``ScraperClient`` como contexto síncrono """
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """ Garante que o cliente seja fechado ao sair do contexto """
        self.close()

    def parse(
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
        result = self.fetch(
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
        """ Seleciona entre ``Retry-After`` e backoff exponencial com jitter"""
        if retry_after is not None:
            return float(retry_after) + random.uniform(0, base)
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
        
    @staticmethod
    def _register_host_retry_window(host: str) -> int | None:
        """ Registra tentativa por host para limiar backoffs em janelas curtas """
        client = get_redis_operational()
        if client is None:
            return None
        try:
            key = f"scraper:host-retry:{host}"
            pipeline = client.pipeline(True)
            pipeline.incr(key)
            pipeline.expire(key, settings.SCRAPER_HOST_RETRY_WINDOW_SECONDS)
            current, _ = pipeline.execute()
            return int(current)
        except Exception:
            return None
        
    @staticmethod
    def _host_retry_exhausted(counter: int | None) -> bool:
        """ Indica se o limite de tentativas por host foi atingido """
        if counter is None:
            return False
        return counter >= settings.SCRAPER_HOST_RETRY_MAX_ATTEMPTS
        