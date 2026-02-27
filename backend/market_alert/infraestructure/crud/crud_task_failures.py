""" CRUD para registros de falhas permanentes de tasks (DLQ). """

from __future__ import annotations

from sqlalchemy.orm import Session

from market_alert.models.models_task_failures import TaskFailure


def create_task_failure(
    db: Session,
    *,
    task_name: str,
    task_id: str,
    exception_class: str | None = None,
    exception_message: str | None = None,
    trace_id: str | None = None,
    retry_count: int = 0,
) -> TaskFailure:
    """ Persiste uma falha permanente de task e retorna o registro criado.

    Commita imediatamente — a falha já foi registrada no Celery e não faz
    parte de nenhuma transação de negócio em andamento.
    """
    failure = TaskFailure(
        task_name=task_name,
        task_id=task_id,
        exception_class=exception_class,
        exception_message=exception_message,
        trace_id=trace_id,
        retry_count=retry_count,
    )
    db.add(failure)
    db.commit()
    db.refresh(failure)
    return failure
