""" Model de auditoria para falhas permanentes de tasks Celery (DLQ).

Campos permitidos em ``task_failures``:
- Metadados técnicos da execução (``task_name``, ``task_id``, ``trace_id``);
- Classe da exceção para classificação operacional;
- Mensagem de exceção sanitizada e truncada, sem payloads sensíveis.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from shared.infra.db import Base


class TaskFailure(Base):
    """ Registro de falha permanente de uma task após esgotar todos os retries.

    Populado automaticamente pelo ``DLQTask.on_failure`` quando uma task
    crítica falha definitivamente. Não possui FK para produtos — é uma
    tabela de auditoria operacional independente do domínio de negócio.
    """

    __tablename__ = "task_failures"

    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    #: Nome completo da task Celery (ex.: market_alert.tasks.collector...)
    task_name = Column(String(255), nullable=False, index=True)

    #: ID único da execução Celery que falhou
    task_id = Column(String(255), nullable=False, index=True)

    #: Tipo da exceção (ex.: ScraperClientError, TimeoutError)
    exception_class = Column(String(255), nullable=True)

    #: Mensagem sanitizada da exceção (com truncamento defensivo)
    exception_message = Column(Text, nullable=True)

    #: Trace ID para correlação com logs e outros eventos do mesmo ciclo
    trace_id = Column(String(255), nullable=True, index=True)

    #: Número de retries já realizados antes da falha permanente
    retry_count = Column(Integer, nullable=False, default=0)

    #: Momento em que a falha permanente foi registrada
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<TaskFailure(id={self.id} task={self.task_name!r} "
            f"exc={self.exception_class} retries={self.retry_count})>"
        )
