""" Hooks de lifecycle do worker Celery.

Ponto de extensão para registrar sinais Celery (worker_ready, worker_shutdown, etc.).
A orquestração contínua foi removida — próxima fase será implementada com Temporal.
"""

from __future__ import annotations

import structlog
from celery import Celery


logger = structlog.get_logger("worker_lifecycle")

def register_worker_signals(celery_app: Celery, process_start_monotonic: float) -> None:
    """ Registra sinais do worker Celery. Ponto de extensão para Temporal. """
    logger.info("worker_lifecycle_registered")
