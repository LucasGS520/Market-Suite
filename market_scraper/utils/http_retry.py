""" Utilitários compartilhados para aplicar retries HTTP com tenacity

O módulo padroniza tentativas extras em downloads do scraper, respeitando
``Retry-After``, expondo métricas e mantendo a API pública estável para os
consumidores atuais.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Awaitable, Callable, Optional

import httpx
import structlog
from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt
from tenacity.wait import wait_base

from market_scraper.core.config_scraper import settings
from shared.metrics.metrics_scraper import (
    SCRAPER_HTTP_RETRIES_TOTAL,
    SCRAPER_HTTP_RETRY_BACKOFF_SECONDS,
)


logger = structlog.get_logger(__name__)

#Códigos HTTP que justificam novas tentativas controladas
_RETRYABLE_STATUS = {429, *range(500, 600)}

@dataclass
class RetryableHTTPError(Exception):
    """ Representa um erro transitório elegível para nova tentativa controlada """
    target: str
    reason: str
    status_code: Optional[int] = None
    retry_after: Optional[float] = None

def _compute_wait_seconds(*, retry_state: RetryCallState, multiplier: float) -> float:
    """ Calcula o tempo de espera aplicando Retry-After quando disponível """
    attempt_index = max(retry_state.attempt_number - 1, 0)
    base_wait = max(0.0, multiplier) * (2 ** attempt_index)

    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, RetryableHTTPError) and exc.retry_after is not None:
        #Retry-After prevalece quando informado pelo servidor de destino
        return exc.retry_after
    
    return base_wait

class _WaitRetryAfter(wait_base):
    """ Combina backoff exponencial simples com prioridade ao Retry-After """
    def __init__(self, *, multiplier: float) -> None:
        self._multiplier = multiplier

    def __call__(self, retry_state: RetryCallState) -> float:
        return _compute_wait_seconds(
            retry_state=retry_state,
            multiplier=self._multiplier,
        )
    
def _parse_retry_after(header_value: Optional[str]) -> Optional[float]:
    """ Traduz o cabeçalho ``Retry-After`` em segundos de espera quando válido """
    if not header_value:
        return None
    
    value = header_value.strip()
    if not value:
        return None
    
    try:
        #Permite segundos fracionários além de valores inteiros
        seconds = float(value)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        
        if parsed is None:
            return None
        
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        delta = (parsed - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)
    else:
        return max(0.0, seconds)
    
def _categorize_reason(status_code: Optional[int]) -> str:
    """ Reduz cardinalidade descrevendo o motivo da nova tentativa """
    if status_code == 429:
        return "too_many_requests"
    if status_code is not None and 500 <= status_code < 600:
        return "server_error"
    return "network_error"

def _before_sleep_factory(
    *,
    target: str,
    multiplier: float,
) -> Callable[[RetryCallState], None]:
    """ Registra métricas e logs antes de aguardar uma nova tentativa """
    def _before_sleep(retry_state: RetryCallState) -> None:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        if not isinstance(exc, RetryableHTTPError):
            return

        wait_seconds = _compute_wait_seconds(
            retry_state=retry_state,
            multiplier=multiplier,
        )

        SCRAPER_HTTP_RETRIES_TOTAL.labels(
            target=target,
            reason=exc.reason,
        ).inc()
        SCRAPER_HTTP_RETRY_BACKOFF_SECONDS.labels(
            target=target,
            reason=exc.reason,
        ).observe(wait_seconds)

        logger.warning(
            "http_retry_scheduled",
            target=target,
            reason=exc.reason,
            wait_seconds=wait_seconds,
        )

    return _before_sleep

def _build_retry_decorator(*, target: str) -> Callable[[Callable[..., Awaitable[httpx.Response]]], Callable[..., Awaitable[httpx.Response]]]:
    """ Monta o decorador de retry reutilizando configurações globais """
    attempts = max(1, settings.SCRAPER_HTTP_RETRIES + 1)
    multiplier = max(0.0, settings.SCRAPER_HTTP_RETRY_BACKOFF_BASE)
    wait_strategy = _WaitRetryAfter(multiplier=multiplier)

    return retry(
        retry=retry_if_exception_type(RetryableHTTPError),
        stop=stop_after_attempt(attempts),
        wait=wait_strategy,
        before_sleep=_before_sleep_factory(target=target, multiplier=multiplier),
        reraise=True,
    )

def _raise_for_retryable_response(
    response: httpx.Response,
    *,
    target: str,
) -> None:
    """ Analisa a resposta HTTP e dispara retry em códigos transitórios """
    if response.status_code not in _RETRYABLE_STATUS:
        return
    
    retry_after = _parse_retry_after(response.headers.get("Retry-After"))
    reason = _categorize_reason(response.status_code)

    message = "Download HTTP elegível para nova tentativa"
    request = response.request
    exc = httpx.HTTPStatusError(message, request=request, response=response)
    raise RetryableHTTPError(
        target=target,
        reason=reason,
        status_code=response.status_code,
        retry_after=retry_after,
    ) from exc

def build_retrying_operation(
    *,
    target: str,
    operation: Callable[[], Awaitable[httpx.Response]],
) -> Callable[[], Awaitable[httpx.Response]]:
    """ Encapsula operação HTTP aplicando retries padronizados """

    retry_decorator = _build_retry_decorator(target=target)

    @retry_decorator
    async def _wrapped_operation() -> httpx.Response:
        try:
            response = await operation()
        except httpx.RequestError as exc:
            reason = _categorize_reason(None)
            raise RetryableHTTPError(
                target=target,
                reason=reason,
            ) from exc
        
        _raise_for_retryable_response(response, target=target)
        return response
    
    return _wrapped_operation

def run_with_retries(
    *,
    target: str,
    operation: Callable[[], Awaitable[httpx.Response]],
) -> Callable[[], Awaitable[httpx.Response]]:
    """ Compatibilidade semântica para usos futuros (alias público) """
    return build_retrying_operation(target=target, operation=operation)

__all__ = [
    "RetryableHTTPError",
    "build_retrying_operation",
    "run_with_retries",
    "_raise_for_retryable_response",
]
