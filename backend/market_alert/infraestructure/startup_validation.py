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

from market_alert.core.config_alert import settings
from shared.infra.db import get_engine


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
    """Verifica Temporal com retry exponencial — falha levanta TemporalConnectionError.

    Número de tentativas configurável via TEMPORAL_HEALTH_MAX_ATTEMPTS (default 10).
    Delays: backoff exponencial com cap de 30s entre tentativas.

    Raises:
        TemporalConnectionError: Temporal inacessível após todas as tentativas.
    """
    import time
    import uuid
    from shared.exceptions import TemporalConnectionError

    try:
        from shared.clients.orchestrator_client import get_temporal_client
    except ImportError:
        logger.error("temporal_module_not_installed")
        raise TemporalConnectionError(
            "Módulo market_orchestrator não instalado",
            attempts=0,
            target="unknown",
        )

    max_attempts = settings.TEMPORAL_HEALTH_MAX_ATTEMPTS
    delays = _build_temporal_delays(max_attempts)
    client = get_temporal_client()
    run_id = uuid.uuid4().hex[:8]  # Correlaciona tentativas desta sequência de boot

    probe_timeout = settings.TEMPORAL_HEALTH_TIMEOUT
    for attempt, delay in enumerate(delays, 1):
        connected = client.probe_connectivity_sync(timeout=probe_timeout)
        if connected:
            logger.info(
                "startup_temporal_ok",
                attempt=attempt,
                max_attempts=max_attempts,
                startup_run_id=run_id,
            )
            return
        has_next = attempt < max_attempts
        logger.info(
            "temporal_health_check_attempt",
            attempt=attempt,
            max_attempts=max_attempts,
            status="transient",
            next_retry_in_seconds=round(delay, 1) if has_next else None,
            startup_run_id=run_id,
        )
        if has_next:
            time.sleep(delay)

    logger.error(
        "temporal_health_check_failed",
        attempts_exhausted=max_attempts,
        startup_run_id=run_id,
    )
    temporal_target = f"{os.getenv('TEMPORAL_HOST', 'temporal')}:{os.getenv('TEMPORAL_PORT', '7233')}"
    raise TemporalConnectionError(
        f"Temporal inacessível após {max_attempts} tentativas de health check",
        attempts=max_attempts,
        target=temporal_target,
    )
    