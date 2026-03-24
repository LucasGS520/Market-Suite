"""Hooks de lifecycle do worker Celery.

Ponto de extensão para registrar sinais Celery (worker_ready, worker_shutdown, etc.).
O Temporal Worker é iniciado exclusivamente pelo container `market_orchestrator`
dedicado no docker-compose — não há thread daemon aqui.
"""

from __future__ import annotations

import structlog
from celery import Celery


logger = structlog.get_logger("worker_lifecycle")


def register_worker_signals(celery_app: Celery, process_start_monotonic: float) -> None:
    """Registra sinais do worker Celery.

    Ponto central para adicionar hooks de startup/shutdown do processo Celery.
    O Temporal Worker não é iniciado aqui — roda no container dedicado `market_orchestrator`.
    """
    logger.info("worker_lifecycle_registered")
