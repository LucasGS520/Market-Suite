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
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

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


async def start_temporal_worker() -> None:
    """ Conecta ao Temporal Server e inicia o worker em loop assíncrono.

    Captura SIGTERM/SIGINT para shutdown gracioso.
    """
    logger.info("temporal_worker_connecting", target=settings.temporal_target)

    client: Client | None = None
    delays = [2, 4, 8, 16, 30]
    for attempt, delay in enumerate(delays, 1):
        try:
            client = await Client.connect(settings.temporal_target, namespace=settings.TEMPORAL_NAMESPACE)
            if attempt > 1:
                logger.info("temporal_worker_connected_after_retry", attempt=attempt, target=settings.temporal_target)
            break
        except Exception as exc:
            logger.warning(
                "temporal_worker_connect_attempt_failed",
                attempt=attempt,
                max_attempts=len(delays),
                target=settings.temporal_target,
                error=str(exc),
            )
            if attempt < len(delays):
                await asyncio.sleep(delay)
            else:
                logger.error("temporal_worker_connect_failed_giving_up", target=settings.temporal_target, error=str(exc))
                return

    assert client is not None

    # Passthrough: módulos com I/O legítimo que não devem ser bloqueados pelo sandbox.
    # pydantic_settings usa Path.expanduser() para resolver env files — operação não-determinística
    # proibida por padrão no sandbox do Temporal. pathlib é adicionado como camada extra de segurança.
    _sandbox_restrictions = SandboxRestrictions.default.with_passthrough_modules(
        "pydantic_settings",
        "pathlib",
    )

    worker = Worker(
        client,
        task_queue=settings.TEMPORAL_TASK_QUEUE,
        workflows=[MonitoredProductWorkflow],
        activities=[
            dispatch_collection,
            query_collection_status,
            persist_workflow_snapshot,
            cleanup_workflow_state,
            fetch_monitored_policy,
        ],
        workflow_runner=SandboxedWorkflowRunner(restrictions=_sandbox_restrictions),
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

    logger.info("temporal_worker_started", task_queue=settings.TEMPORAL_TASK_QUEUE)

    async with worker:
        await shutdown_event.wait()

    logger.info("temporal_worker_stopped")

def run_worker() -> None:
    """ Ponto de entrada síncrono para execução via subprocess ou thread."""
    asyncio.run(start_temporal_worker())


if __name__ == "__main__":
    run_worker()
