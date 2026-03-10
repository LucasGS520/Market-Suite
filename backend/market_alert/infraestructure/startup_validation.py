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

    Args:
        strict: Quando ``True``, interrompe o processo em caso de falha.

    Returns:
        ``True`` quando todas as validações passam, caso contrário ``False``.
    """
    postgres_ok = _validate_postgres()
    redis_ok = _validate_redis()
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
    