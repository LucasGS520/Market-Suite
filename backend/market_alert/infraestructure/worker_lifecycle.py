""" Hooks de lifecycle do worker Celery.

Ponto de extensão para registrar sinais Celery (worker_ready, worker_shutdown, etc.).
Inicia o Temporal Worker Python em thread daemon quando o worker Celery estiver pronto.
"""

from __future__ import annotations

import asyncio
import threading

import structlog
from celery import Celery
from celery.signals import worker_ready


logger = structlog.get_logger("worker_lifecycle")

def register_worker_signals(celery_app: Celery, process_start_monotonic: float) -> None:
    """ Registra sinais do worker Celery e conecta o Temporal Worker ao sinal worker_ready """

    @worker_ready.connect
    def _on_worker_ready(sender: object = None, **kwargs: object) -> None:
        """ Inicia o Temporal Worker em thread daemon após o worker Celery estar pronto """
        try:
            from market_orchestrator.worker import start_temporal_worker
        except ImportError:
            logger.warning("temporal_worker_import_failed_skipping")
            return

        def _run() -> None:
            asyncio.run(start_temporal_worker())

        thread = threading.Thread(target=_run, daemon=True, name="temporal-worker")
        thread.start()
        logger.info("temporal_worker_thread_started")

    logger.info("worker_lifecycle_registered")
