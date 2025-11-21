""" Implementação simplificada de rate limit por host usando Redis """

from __future__ import annotations

import logging
from typing import Callable, Tuple

from redis import Redis

from shared.utils.redis_client import consume_leaky_bucket


logger = logging.getLogger(__name__)

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
        """ Incrementa contador para o host e indica se há capacidade """
        client = self._client()
        if client is None:
            return True
        
        key = f"{self._namespace}:{host}"
        try:
            pipeline = client.pipeline(True)
            pipeline.incr(key)
            pipeline.expire(key, self._window_seconds)
            current, _ = pipeline.execute()
        except Exception as exc:
            logger.warning("rate_limiter_redis_failure: %s", exc)
            return True
        
        return int(current) <= self._max_requests
    
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
