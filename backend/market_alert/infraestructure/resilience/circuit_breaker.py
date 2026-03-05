""" Circuit breaker baseado em Redis para proteger integrações externas """

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from redis import Redis


logger = logging.getLogger(__name__)

class CircuitBreaker:
    """ Gerencia abertura de circuito quando falhas consecutivas ocorrem """
    def __init__(
        self,
        client_factory: Callable[[], Redis | None],
        *,
        failure_threshold: int,
        failure_window: int,
        cooldown_seconds: int,
        namespace: str = "scraper:circuit",
    ) -> None:
        self._client_factory = client_factory
        self._failure_threshold = max(1, failure_threshold)
        self._failure_window = max(1, failure_window)
        self._cooldown_seconds = max(1, cooldown_seconds)
        self._namespace = namespace

    def _client(self) -> Redis | None:
        """ Obtém cliente Redis tolerando indisponibilidade """
        try:
            return self._client_factory()
        except Exception as exc:
            logger.warning("circuit_breaker_client_error: %s", exc)
            return None
        
    def _failures_key(self, host: str) -> str:
        return f"{self._namespace}:failures:{host}"
    
    def _open_key(self, host: str) -> str:
        return f"{self._namespace}:open:{host}"
    
    def is_open(self, host: str) -> bool:
        """ Verifica se o circuito está aberto para o host """
        client = self._client()
        if client is None:
            return False
        try:
            ttl = client.ttl(self._open_key(host))
        except Exception as exc:
            logger.warning("circuit_breaker_ttl_error: %s", exc)
            return False
        return ttl is not None and ttl > 0
    
    def record_success(self, host: str) -> None:
        """ Zera contadores após uma chamada bem-sucedida """
        client = self._client()
        if client is None:
            return
        try:
            open_key = self._open_key(host)
            was_open = bool(client.exists(open_key))
            client.delete(self._failures_key(host))
            if was_open:
                client.delete(open_key)
                logger.info("host_unblocked", extra={"host": host})
        except Exception as exc:
            logger.warning("circuit_breaker_reset_error: %s", exc)

    def record_failure(self, host: str) -> None:
        """ Incrementa contador e abre circuito quando limiar é atingido """
        client = self._client()
        if client is None:
            return
        
        failures_key = self._failures_key(host)
        open_key = self._open_key(host)
        try:
            pipeline = client.pipeline(True)
            pipeline.incr(failures_key)
            pipeline.expire(failures_key, self._failure_window)
            current, _ = pipeline.execute()
        except Exception as exc:  # pragma: no cover
            logger.warning("circuit_breaker_failure_increment_error: %s", exc)
            return

        if int(current) >= self._failure_threshold:
            try:
                until = datetime.now(timezone.utc) + timedelta(seconds=self._cooldown_seconds)
                pipeline = client.pipeline(True)
                pipeline.set(open_key, until.isoformat(), ex=self._cooldown_seconds)
                pipeline.delete(failures_key)
                pipeline.execute()
                logger.warning(
                    "host_blocked",
                    extra={"host": host, "cooldown_seconds": self._cooldown_seconds}
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("circuit_breaker_open_error: %s", exc)
                