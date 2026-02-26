""" Controle de vazão por host usando Redis com fallback seguro """

from __future__ import annotations

import logging
import random
from typing import Callable, Tuple

from redis import Redis

from shared.utils.redis_client import (
    consume_leaky_bucket,
    consume_token_bucket,
    get_redis_client,
    set_key_with_ttl,
)


logger = logging.getLogger(__name__)

LOCK_RETRY_BASE_SECONDS = 5
LOCK_RETRY_MAX_SECONDS = 60
LOCK_RETRY_JITTER_RATIO = 0.2
SCRAPE_RETRY_BASE_SECONDS = 30
SCRAPE_RETRY_MAX_SECONDS = 15 * 60
SCRAPE_RETRY_JITTER_RATIO = 0.3

class RateLimiter:
    """ Controla volume de chamadas para um host específico """
    def __init__(
        self,
        client_factory: Callable[[], Redis | None],
        *,
        max_requests: int,
        window_seconds: int,
        namespace: str = "scraper:rate",
    ) -> None:
        self._client_factory = client_factory
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._namespace = namespace

    def _client(self) -> Redis | None:
        """ Obtém cliente Redis mantendo tolerância a falhas """
        try:
            return self._client_factory()
        except Exception as exc:
            logger.warning("rate_limiter_client_error: %s", exc)
            return None
        
    def allow(self, host: str) -> bool:
        """ Avalia o limite por host usando *token bucket* em Redis """
        client = self._client()
        if client is None:
            return True
        
        key = f"{self._namespace}:{host}"
        allowed, _ = consume_token_bucket(
            key,
            capacity=self._max_requests,
            refill_rate_per_second=self._max_requests / self._window_seconds,
            client=client,
        )
        return allowed
    
def parse_rate_limit_config(rate_limit: str) -> Tuple[int, int] | None:
    """ Interpreta configurações no formato ``valor/unidade`` retornando capacidade e janela 
    
    Mantém compatibilidade com unidades abreviadas em segundos, minutos ou horas,
    ignorando configurações inválidas para evitar bloqueios acidentais.
    """
    cleaned = (rate_limit or "").strip()
    if not cleaned or "/" not in cleaned:
        return None
    
    amount_part, window_part = cleaned.split("/", 1)
    try:
        max_requests = int(amount_part)
    except ValueError:
        logger.warning("invalid_rate_limit_config", raw=rate_limit)
        return None
    
    unit = window_part.strip().lower()
    unit_mapping = {
        "s": 1,
        "sec": 1,
        "secs": 1,
        "second": 1,
        "seconds": 1,
        "m": 60,
        "min": 60,
        "mins": 60,
        "minute": 60,
        "minutes": 60,
        "h": 3600,
        "hour": 3600,
        "hours": 3600,
    }

    if unit.isdigit():
        window_seconds = int(unit)
    else:
        window_seconds = unit_mapping.get(unit)

    if not window_seconds:
        logger.warning("unsupported_rate_limit_unit", raw=rate_limit)
        return None
    
    if max_requests <= 0 or window_seconds <= 0:
        logger.warning("non_positive_rate_limit", raw=rate_limit)
        return None

    return max_requests, window_seconds


def allow_with_leaky_bucket(
    bucket_key: str,
    *,
    rate_limit: Tuple[int, int] | str | None,
) -> bool:
    """ Aplica controle de vazão via *leaky bucket* considerando a configuração informada """

    if isinstance(rate_limit, str):
        parsed_limit = parse_rate_limit_config(rate_limit)
    else:
        parsed_limit = rate_limit

    if not parsed_limit:
        return True

    max_requests, window_seconds = parsed_limit
    leak_rate = max_requests / window_seconds

    allowed, _ = consume_leaky_bucket(
        bucket_key,
        capacity=max_requests,
        leak_rate_per_second=leak_rate,
    )
    return allowed

def _compute_lock_retry_delay(
    attempt: int,
    *,
    base_seconds: int = LOCK_RETRY_BASE_SECONDS,
    max_seconds: int = LOCK_RETRY_MAX_SECONDS,
    jitter_ratio: float = LOCK_RETRY_JITTER_RATIO,
) -> int:
    """ Calcula atraso para retry com backoff exponencial e jitter leve """
    sanitized_attempt = max(1, attempt)
    exponential_delay = base_seconds * (2 ** (sanitized_attempt - 1))
    capped_delay = min(exponential_delay, max_seconds)
    #Aplica jitter leve para evitar colisão de reexecuções simultâneas
    jitter_multiplier = 1 + ((random.random() * 2) - 1) * jitter_ratio
    delay = int(max(1, capped_delay * jitter_multiplier))
    return delay

def _compute_scrape_retry_delay(
    attempt: int,
    *,
    base_seconds: int = SCRAPE_RETRY_BASE_SECONDS,
    max_seconds: int = SCRAPE_RETRY_MAX_SECONDS,
    jitter_ratio: float = SCRAPE_RETRY_JITTER_RATIO,
    retry_after: int | None = None,
) -> int:
    """ Calcula atraso para falhas temporárias usando backoff e ``Retry-After`` """
    if retry_after is not None and retry_after > 0:
        return int(min(retry_after, max_seconds))
    return _compute_lock_retry_delay(
        attempt,
        base_seconds=base_seconds,
        max_seconds=max_seconds,
        jitter_ratio=jitter_ratio,
    )

def _increment_invalid_url_attempt(
    product_id: str | None,
    *,
    ttl_seconds: int,
) -> int | None:
    """ Incrementa contador de URls inválidas para limitar reprocessamentos """
    if product_id is None:
        return None
    client = get_redis_client()
    if client is None:
        return None
    
    key = f"market_alert:scrape_invalid:{product_id}"
    try:
        pipeline = client.pipeline(True)
        pipeline.incr(key)
        pipeline.expire(key, ttl_seconds)
        current, _ = pipeline.execute()
        return int(current)
    except Exception:
        return None
    
def _reset_invalid_url_attempt(product_id: str | None) -> None:
    """ Reseta contador de URLs inválidas após bloqueio """
    if product_id is None:
        return
    client = get_redis_client()
    if client is None:
        return
    try:
        client.delete(f"market_alert:scrape_invalid:{product_id}")
    except Exception:
        pass

def _increment_temporary_failure_attempt(
    product_id: str | None,
    *,
    ttl_seconds: int,
) -> int | None:
    """ Incrementa contador de falhas temporárias para limitar reprocessamentos """
    if product_id is None:
        return None
    client = get_redis_client()
    if client is None:
        return None
    
    key = f"market_alert:scrape_retry:{product_id}"
    try:
        pipeline = client.pipeline(True)
        pipeline.incr(key)
        pipeline.expire(key, ttl_seconds)
        current, _ = pipeline.execute()
        return int(current)
    except Exception:
        return None
    
def _reset_temporary_failure_attempt(product_id: str | None) -> None:
    """ Reseta contador de falhas temporárias quando o limite é atingido """
    if product_id is None:
        return
    client = get_redis_client()
    if client is None:
        return
    try:
        client.delete(f"market_alert:scrape_retry:{product_id}")
    except Exception:
        pass

def _register_scrape_cooldown(
    product_id: str | None,
    *,
    ttl_seconds: int,
) -> bool | None:
    """ Registra cooldown para reduzir coletas consecutivas """
    if product_id is None:
        return None
    return set_key_with_ttl(
        f"market_alert:scrape_cooldown:{product_id}",
        "1",
        ttl_seconds,
        only_if_absent=True,
    )

def _resolve_cooldown_seconds(product_id: str) -> int | None:
    """ Verifica se há cooldown ativo para evitar coletas consecutivas """
    client = get_redis_client()
    if client is None:
        return None
    try:
        ttl = client.ttl(f"market_alert:scrape_cooldown:{product_id}")
    except Exception:
        return None
    if ttl is None or ttl < 0:
        return None
    return int(ttl)


__all__ = [
    "RateLimiter",
    "allow_with_leaky_bucket",
    "parse_rate_limit_config",
    "_compute_lock_retry_delay",
    "_compute_scrape_retry_delay",
    "_increment_invalid_url_attempt",
    "_reset_invalid_url_attempt",
    "_increment_temporary_failure_attempt",
    "_reset_temporary_failure_attempt",
    "_register_scrape_cooldown",
    "_resolve_cooldown_seconds",
]
