""" Validação de dependências críticas no startup da aplicação.

Este módulo concentra *health checks* obrigatórios de infraestrutura para
permitir falha rápida quando Redis ou PostgreSQL estiverem indisponíveis.

Regra operacional:
    - ``strict=True``  -> lança ``RuntimeError`` para interromper o processo.
    - ``strict=False`` -> apenas registra erro e retorna ``False``.
"""

from __future__ import annotations

import redis
import structlog
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from market_alert.core.config_alert import settings
from shared.infra.db import get_engine


logger = structlog.get_logger("startup_validation")

def validate_startup_dependencies(*, strict: bool = True) -> bool:
    """ Valida PostgreSQL e Redis antes de liberar o serviço.

    A função executa consultas mínimas (``SELECT 1`` e ``PING``) para garantir
    conectividade básica. Isso reduz o risco de subir API/worker em estado
    degradado e só descobrir falhas após receber carga.

    Temporal é verificado de forma não-bloqueante: falha gera warning mas NÃO
    impede o startup (fallback para Celery continua disponível).

    Args:
        strict: Quando ``True``, interrompe o processo em caso de falha de
                PostgreSQL ou Redis.

    Returns:
        ``True`` quando todas as validações passam, caso contrário ``False``.
    """
    postgres_ok = _validate_postgres()
    redis_ok = _validate_redis()
    _validate_temporal_nonblocking()
    is_valid = postgres_ok and redis_ok

    if is_valid:
        logger.info("startup_dependencies_validated", postgres=True, redis=True)
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

def _validate_temporal_nonblocking() -> None:
    """ Verifica Temporal com retry exponencial — falha gera warning, nunca RuntimeError.

    Tenta conectar até 5 vezes com backoff crescente antes de declarar fallback.
    Delays totais: 2+4+8+16 = 30 segundos de espera máxima entre tentativas.
    """
    import time

    try:
        from market_orchestrator.alert.alert_client import get_temporal_client
    except ImportError:
        logger.warning("temporal_module_not_installed", fallback="celery_available")
        return

    delays = [2, 4, 8, 16, 30]
    client = get_temporal_client()
    for attempt, delay in enumerate(delays, 1):
        connected = client.probe_connectivity_sync()
        if connected:
            logger.info("startup_temporal_ok", attempt=attempt)
            return
        next_delay = delay if attempt < len(delays) else None
        logger.warning(
            "temporal_health_check_attempt",
            attempt=attempt,
            max_attempts=len(delays),
            next_delay=next_delay,
            fallback="celery_available",
        )
        if next_delay is not None:
            time.sleep(next_delay)

    logger.warning(
        "temporal_health_check_failed",
        severity="warning",
        fallback="celery_available",
    )
    