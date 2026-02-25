""" Tarefas Celery do coletor contínuo.

Este módulo mantém apenas o contrato de transporte do Celery e delega a
execução operacional para ``continuous_collector_manager``, reduzindo o
acoplamento entre task wrappers e regras de orquestração.
"""

from __future__ import annotations

from typing import Any

import structlog

from shared.infra.db import SessionLocal

from market_alert.core.celery_app import celery_app
from market_alert.services.continuous_collector_manager import (
    finalize_processing_requeue as _finalize_processing_requeue,
    finalize_processing_requeue_error as _finalize_processing_requeue_error,
    run_collection_loop,
)


logger = structlog.get_logger("continuous_collector_task")

@celery_app.task(
    name="market_alert.tasks.continuous_collector_task.finalize_processing_requeue",
    queue="monitor",
)
def finalize_processing_requeue(
    collect_result: Any,
    monitored_id: str,
    trace_id: str | None = None,
) -> None:
    """Wrapper Celery para finalizar coleta e reenfileirar o monitorado."""
    #Cada task abre sua sessão no ponto de entrada para manter o ciclo de vida explícito.
    with SessionLocal() as db:
        _finalize_processing_requeue(
            db=db,
            collect_result=collect_result,
            monitored_id=monitored_id,
            trace_id=trace_id,
        )


@celery_app.task(
    name="market_alert.tasks.continuous_collector_task.finalize_processing_requeue_error",
    queue="monitor",
)
def finalize_processing_requeue_error(
    request,
    exc,
    traceback,
    monitored_id: str,
    trace_id: str | None = None,
) -> None:
    """Wrapper Celery para tratar falhas inesperadas na coleta."""
    #O callback de erro também segue a regra de sessão única por execução.
    with SessionLocal() as db:
        _finalize_processing_requeue_error(
            db=db,
            monitored_id=monitored_id,
            trace_id=trace_id,
        )


@celery_app.task(
    bind=True,
    name="market_alert.tasks.continuous_collector_task.run_continuous_collector",
    queue="monitor",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": None},
    time_limit=None,
    soft_time_limit=None,
)
def run_continuous_collector(self) -> None:
    """Task principal que delega o loop contínuo ao serviço de gerenciamento."""
    task_id = getattr(self.request, "id", None)
    logger.bind(task_id=task_id).info("continuous_collector_task_delegated")
    with SessionLocal() as db:
        run_collection_loop(
            db=db,
            task_request=getattr(self, "request", None),
            task_id=task_id,
        )
