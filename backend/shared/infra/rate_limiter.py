""" Interface e implementação Redis para rate limiting.

Define o contrato de rate limiting como Protocol, permitindo que
implementações alternativas (ex.: in-memory para testes) sejam usadas
sem alterar o código que as consome.

Uso::

    from shared.utils.redis_client import get_redis_operational
    from shared.infra.rate_limiter import RedisRateLimiter

    limiter = RedisRateLimiter(get_redis_operational())

    # Verifica antes de registrar tentativa (padrão para brute-force)
    if not limiter.check("bf:192.168.1.1", max_attempts=5, window_seconds=300):
        raise HTTPException(429, "Muitas tentativas")

    # Incrementa e verifica em uma operação (padrão para rate limit de endpoint)
    count = limiter.increment("rl:endpoint:ip", window_seconds=60)
    if count > 10:
        raise HTTPException(429, "Limite excedido")
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import structlog

logger = structlog.get_logger("infra.rate_limiter")


@runtime_checkable
class RateLimiter(Protocol):
    """ Contrato para verificação de limites de taxa.

    Qualquer objeto com os métodos abaixo implementa este protocolo,
    incluindo implementações in-memory para testes. O decorator
    ``@runtime_checkable`` permite usar ``isinstance()`` para verificar.
    """

    def check(
        self,
        key: str,
        *,
        max_attempts: int,
        window_seconds: int,
    ) -> bool:
        """ Verifica se a chave ainda está dentro do limite.

        Returns:
            True se a requisição é permitida. False se excedeu o limite.
        """
        ...

    def increment(
        self,
        key: str,
        *,
        window_seconds: int,
    ) -> int:
        """ Incrementa o contador e retorna o valor atual.

        Define o TTL automaticamente na primeira chamada (quando count == 1).

        Returns:
            Valor atual do contador após incremento.
        """
        ...

    def reset(self, key: str) -> None:
        """ Zera o contador para a chave informada. """
        ...

class RedisRateLimiter:
    """ Implementação de rate limiting baseada em contadores Redis.

    Usa ``INCR`` + ``EXPIRE`` para contagem com janela deslizante.
    Degrada de forma segura se o Redis estiver indisponível — as operações
    retornam valores que permitem a ação (True/0) em vez de bloquear.

    Args:
        redis_client: Instância de cliente Redis (síncrona).
    """

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def check(
        self,
        key: str,
        *,
        max_attempts: int,
        window_seconds: int,
    ) -> bool:
        """ Verifica se a chave ainda está dentro do limite.

        Não incrementa o contador — use ``increment()`` para registrar
        a tentativa separadamente.

        Returns:
            True se permitido. False se o limite foi excedido.
        """
        if self._redis is None:
            logger.warning("redis_rate_limiter_unavailable", operation="check", key=key)
            return True

        try:
            current = int(self._redis.get(key) or 0)
            allowed = current < max_attempts
            logger.debug(
                "redis_rate_limiter_check",
                key=key,
                current=current,
                max_attempts=max_attempts,
                window_seconds=window_seconds,
                allowed=allowed,
            )
            if not allowed:
                logger.info(
                    "redis_rate_limiter_blocked",
                    key=key,
                    attempts=current,
                    max_attempts=max_attempts,
                )
            return allowed
        except Exception:
            logger.warning("redis_rate_limiter_check_failed", key=key, exc_info=True)
            #Degradação segura: permite a operação se Redis falhar.
            return True

    def increment(
        self,
        key: str,
        *,
        window_seconds: int,
    ) -> int:
        """ Incrementa o contador e define TTL na primeira chamada.

        Returns:
            Valor atual após incremento. Retorna 0 em caso de falha.
        """
        try:
            count = self._redis.incr(key)
            if count == 1:
                #TTL é definido apenas no primeiro incremento para manter a janela
                self._redis.expire(key, window_seconds)
            logger.debug(
                "redis_rate_limiter_increment",
                key=key,
                count=int(count),
                window_seconds=window_seconds,
            )
            return int(count)
        except Exception:
            logger.warning("redis_rate_limiter_increment_failed", key=key, exc_info=True)
            return 0

    def reset(self, key: str) -> None:
        """Remove o contador do Redis."""
        if self._redis is None:
            logger.warning("redis_rate_limiter_unavailable", operation="reset", key=key)
            return
        
        try:
            self._redis.delete(key)
            logger.debug("redis_rate_limiter_reset", key=key)
        except Exception:
            logger.warning("redis_rate_limiter_reset_failed", key=key, exc_info=True)
