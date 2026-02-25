""" Task consumidora da fila dead_letter (Dead Letter Queue).

Recebe mensagens de tasks que falharam permanentemente (retries esgotados),
persiste o registro em ``task_failures`` para auditoria e emite log
estruturado para monitoramento operacional.

Casca fina: toda persistência é delegada a ``crud_task_failures``.
"""

from __future__ import annotations

import structlog

from shared.infra.db import SessionLocal
from shared.utils import sanitize_exception_message

from market_alert.core.celery_app import celery_app
from market_alert.crud.crud_task_failures import create_task_failure


logger = structlog.get_logger("dlq_handler")


@celery_app.task(
    bind=True,
    name="market_alert.tasks.dlq_handler.handle_dead_letter",
    queue="dead_letter",
    max_retries=0,
    acks_late=True,
)
def handle_dead_letter(
    self,
    *,
    task_name: str,
    task_id: str,
    exception_class: str | None = None,
    exception_message: str | None = None,
    retry_count: int = 0,
    trace_id: str | None = None,
) -> None:
    """ Persiste falha permanente de task e notifica operadores via log.

    Não relança exceções — uma falha no handler da DLQ não deve criar
    loops. Erros de persistência são logados e silenciados.
    """
    bound = logger.bind(
        task_name=task_name,
        task_id=task_id,
        exception_class=exception_class,
        retry_count=retry_count,
        trace_id=trace_id,
    )
    sanitized_exception_message = sanitize_exception_message(exception_message or "", max_length=500)
    bound.error(
        "task_permanent_failure",
        #Persistimos e logamos sempre a versão sanitizada para reduzir vazamento de dados sensíveis.
        exception_message=sanitized_exception_message,
    )

    try:
        with SessionLocal() as db:
            create_task_failure(
                db,
                task_name=task_name,
                task_id=task_id,
                exception_class=exception_class,
                exception_message=sanitized_exception_message,
                trace_id=trace_id,
                retry_count=retry_count,
            )
        bound.info("dlq_failure_persisted")
    except Exception:
        bound.exception("dlq_persistence_failed")
