""" Implementação simplificada de rate limit por host usando Redis """

from __future__ import annotations

import logging
from typing import Callable

from redis import Redis


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
            logger.warning("rate_limiter_client_error", error=str(exc))
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
            logger.warning("rate_limiter_redis_failure", error=str(exc))
            return True
        
        return int(current) <= self._max_requests
    