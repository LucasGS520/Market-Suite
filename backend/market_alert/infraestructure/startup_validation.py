"""Validação de dependências críticas no startup da aplicação.

Este módulo concentra *health checks* obrigatórios de infraestrutura para
permitir falha rápida quando Redis, PostgreSQL ou Temporal estiverem indisponíveis.

Regra operacional:
    - PostgreSQL / Redis: ``strict=True`` lança ``RuntimeError``.
    - Temporal: lança ``TemporalConnectionError`` ao esgotar tentativas — nunca silenciado.
"""

from __future__ import annotations

import os

import redis
import structlog
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from shared.infra.db import get_engine
from shared.utils.async_utils import run_sync_coro

from market_alert.core.config_alert import settings


logger = structlog.get_logger("startup_validation")

def validate_startup_dependencies(*, strict: bool = True) -> bool:
    """Valida PostgreSQL, Redis e Temporal antes de liberar o serviço.

    Executa consultas mínimas (``SELECT 1`` e ``PING``) para garantir
    conectividade básica. Temporal é verificado com retry robusto — falha
    levanta ``TemporalConnectionError`` independente do flag ``strict``.

    Args:
        strict: Quando ``True``, interrompe o processo em caso de falha de
                PostgreSQL ou Redis.

    Returns:
        ``True`` quando todas as validações passam, caso contrário ``False``.

    Raises:
        RuntimeError: PostgreSQL ou Redis indisponível com ``strict=True``.
        TemporalConnectionError: Temporal inacessível após todas as tentativas.
    """
    postgres_ok = _validate_postgres()
    redis_ok = _validate_redis()
    _validate_temporal()          # Propaga TemporalConnectionError se falhar
    is_valid = postgres_ok and redis_ok

    if is_valid:
        logger.info("startup_dependencies_validated", postgres=True, redis=True, temporal=True)
        return True

    if strict:
        raise RuntimeError("Falha na validação de startup: PostgreSQL/Redis indisponível")
    return False

def _validate_postgres() -> bool:
    """ Executa consulta simples no PostgreSQL para confirmar conectividade."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("startup_postgres_ok")
        return True
    except SQLAlchemyError:
        logger.exception("startup_postgres_unavailable")
        return False

def _validate_redis() -> bool:
    """ Executa ping no Redis para confirmar conectividade."""
    try:
        redis_client = redis.from_url(settings.redis_operational_url)
        redis_client.ping()
        logger.info("startup_redis_ok")
        return True
    except Exception:
        logger.exception("startup_redis_unavailable")
        return False

def _build_temporal_delays(max_attempts: int) -> list[float]:
    """Backoff exponencial (cap 30s) com jitter ±15% para evitar sincronização entre containers."""
    import random
    base = [min(2 ** (i + 1), 30) for i in range(max_attempts)]
    return [d + random.uniform(0, d * 0.15) for d in base]

def _validate_temporal() -> None:
    """Valida Temporal tentando conectar diretamente — falha levanta TemporalConnectionError.

    Esta função é SÍNCRONA por design e deve ser invocada fora do event loop do
    FastAPI. Em ``main.py``, o hook de startup usa ``asyncio.to_thread()`` para
    executá-la em uma thread separada, evitando deadlock no event loop do uvicorn.

    Internamente usa ``run_sync_coro`` (via ``asyncio.run()``) para conectar ao
    Temporal SDK. Chamar esta função diretamente do event loop causaria deadlock
    imediato — use sempre ``await asyncio.to_thread(validate_startup_dependencies)``.

    Conecta ao namespace padrão com retry exponencial. Se consegue conectar e
    desconectar cleanly, Temporal está pronto para uso.

    Raises:
        TemporalConnectionError: Temporal inacessível após todas as tentativas.
    """
    import time
    import uuid
    from temporalio.client import Client
    from shared.exceptions import TemporalConnectionError

    max_attempts = settings.TEMPORAL_HEALTH_MAX_ATTEMPTS
    delays = _build_temporal_delays(max_attempts)
    run_id = uuid.uuid4().hex[:8]

    temporal_target = f"{os.getenv('TEMPORAL_HOST', 'temporal')}:{os.getenv('TEMPORAL_PORT', '7233')}"
    namespace = os.getenv('TEMPORAL_NAMESPACE', 'default')

    logger.info(
        "startup_temporal_validation_starting",
        target=temporal_target,
        namespace=namespace,
        max_attempts=max_attempts,
        startup_run_id=run_id,
    )

    last_exc: Exception | None = None
    for attempt, delay in enumerate(delays, 1):
        try:
            #Conecta diretamente ao Temporal usando SDK oficial
            run_sync_coro(
                Client.connect(
                    temporal_target,
                    namespace=namespace,
                )
            )

            logger.info(
                "startup_temporal_ok",
                attempt=attempt,
                max_attempts=max_attempts,
                target=temporal_target,
                namespace=namespace,
                startup_run_id=run_id,
            )
            return  #Sucesso — Temporal está pronto

        except Exception as exc:
            last_exc = exc
            has_next = attempt < max_attempts
            logger.warning(
                "temporal_health_check_attempt",
                attempt=attempt,
                max_attempts=max_attempts,
                target=temporal_target,
                namespace=namespace,
                status="transient",
                next_retry_in_seconds=round(delay, 1) if has_next else None,
                startup_run_id=run_id,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            if has_next:
                time.sleep(delay)

    #Todas as tentativas falharam
    logger.error(
        "temporal_health_check_failed",
        attempts_exhausted=max_attempts,
        target=temporal_target,
        namespace=namespace,
        startup_run_id=run_id,
        last_error=str(last_exc),
    )

    raise TemporalConnectionError(
        f"Temporal inacessível após {max_attempts} tentativas (target={temporal_target})",
        attempts=max_attempts,
        target=temporal_target,
    ) from last_exc
    