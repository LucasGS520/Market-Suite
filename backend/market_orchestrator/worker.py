""" Temporal Worker do market_orchestrator.

Registra o MonitoredProductWorkflow e todas as Activities na task queue
"market-orchestrator". Executa em loop assíncrono próprio.
"""
from __future__ import annotations

import asyncio
import signal
import sys

import structlog
from temporalio.client import Client
from temporalio.worker import Worker

from market_orchestrator.activities import (
    cleanup_workflow_state,
    dispatch_collection,
    fetch_monitored_policy,
    persist_workflow_snapshot,
    query_collection_status,
)
from market_orchestrator.core.config_orchestrator import settings
from market_orchestrator.workflow import MonitoredProductWorkflow


logger = structlog.get_logger("orchestrator.worker")

TASK_QUEUE = "market-orchestrator"

async def start_temporal_worker() -> None:
    """ Conecta ao Temporal Server e inicia o worker em loop assíncrono.

    Captura SIGTERM/SIGINT para shutdown gracioso.
    """
    logger.info("temporal_worker_connecting", target=settings.temporal_target)

    try:
        client = await Client.connect(settings.temporal_target, namespace=settings.TEMPORAL_NAMESPACE)
    except Exception as exc:
        logger.error("temporal_worker_connect_failed", error=str(exc))
        return

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[MonitoredProductWorkflow],
        activities=[
            dispatch_collection,
            query_collection_status,
            persist_workflow_snapshot,
            cleanup_workflow_state,
            fetch_monitored_policy,
        ],
    )

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _request_shutdown(*_: object) -> None:
        logger.info("temporal_worker_shutdown_requested")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except (NotImplementedError, ValueError):
            #Windows não suporta add_signal_handler em todos os contextos
            signal.signal(sig, _request_shutdown)  # type: ignore[arg-type]

    logger.info("temporal_worker_started", task_queue=TASK_QUEUE)

    async with worker:
        await shutdown_event.wait()

    logger.info("temporal_worker_stopped")

def run_worker() -> None:
    """ Ponto de entrada síncrono para execução via subprocess ou thread."""
    asyncio.run(start_temporal_worker())


if __name__ == "__main__":
    run_worker()
