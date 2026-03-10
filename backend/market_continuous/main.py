""" Entry point standalone do coletor contínuo.

Executa o loop de monitoramento como processo independente,
sem acoplamento com o worker Celery de monitoramento.

Uso::

    cd backend && python -m market_continuous.main

Variáveis de ambiente relevantes:
    CONTINUOUS_COLLECTOR_AUTOSTART          — '1' para habilitar
    CONTINUOUS_COLLECTOR_LOCK_TTL_SECONDS   — TTL do lock Redis
    CONTINUOUS_WORKER_BATCH_SIZE            — Itens por ciclo
    CONTINUOUS_WORKER_POLL_INTERVAL         — Pausa entre ciclos (s)
    CONTINUOUS_WORKER_PROCESSING_TTL_SECONDS — TTL para reclaim de itens

Shutdown gracioso:
    SIGTERM é capturado. O loop conclui a iteração atual antes de parar.
"""

from __future__ import annotations

import signal
import sys

import structlog

from market_alert.infraestructure.logging_config import setup_worker_logging


setup_worker_logging()
logger = structlog.get_logger("market_continuous.main")

_shutdown_requested = False

def _handle_sigterm(signum, frame) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("market_continuous_shutdown_requested", signal=signum)

def run() -> None:
    """ Inicializa e executa o loop contínuo. """
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    logger.info("market_continuous_starting")

    from shared.infra.db import SessionLocal
    from market_continuous.orchestrator.manager import run_collection_loop
    from market_continuous.orchestrator.reconciliation import reconcile_collection_queue

    # Reconcilia a fila na inicialização para garantir consistência DB ↔ Redis
    with SessionLocal() as db:
        stats = reconcile_collection_queue(db)
        logger.info("market_continuous_reconciliation_done", **stats)

    # Executar o loop contínuo com sessão dedicada
    with SessionLocal() as db:
        run_collection_loop(db=db, task_request=None)

    logger.info("market_continuous_stopped")


if __name__ == "__main__":
    run()
    sys.exit(0)
