""" Gravação de falhas permanentes de tasks na DLQ via Redis Streams.

Substitui o fluxo antigo de ``send_task → dead_letter queue → PostgreSQL``
por um XADD direto ao stream ``settings.CELERY_DLQ_STREAM_NAME``.
Vantagens: sem dependência de worker, menor latência, sem tabela de banco.

Uso::

    from market_alert.infraestructure.celery.redis_dlq_handler import write_to_dlq

    write_to_dlq(
        task_id=task_id,
        task_name=self.name,
        queue="scraping",
        exception=exc,
        trace_id=trace_id,
        retry_count=retry_count,
        max_retries=self.max_retries,
        payload_summary=None,
    )
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from shared.utils import sanitize_exception_message
from shared.infra.redis.streams import xadd_event


logger = logging.getLogger(__name__)

def write_to_dlq(
    *,
    task_id: str,
    task_name: str,
    queue: str,
    exception: Exception,
    trace_id: str | None,
    retry_count: int,
    max_retries: int,
    payload_summary: str | None = None,
) -> bool:
    """ Serializa e grava um evento de falha permanente no stream DLQ.

    Retorna ``True`` em caso de sucesso, ``False`` em caso de falha.
    Nunca propaga exceção — o caller (DLQTask.on_failure) já está em
    contexto de falha e não deve receber nova exceção.
    """
    from market_alert.core.config_alert import settings

    exception_type = type(exception).__name__
    exception_message = sanitize_exception_message(str(exception), max_length=500)

    fields: dict[str, str] = {
        "task_id": task_id,
        "task_name": task_name,
        "queue": queue,
        "exception_type": exception_type,
        "exception_message": exception_message,
        "retry_count": str(retry_count),
        "max_retries": str(max_retries),
        "trace_id": trace_id or "",
        "payload_summary": payload_summary or "",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    event_id = xadd_event(
        key=settings.CELERY_DLQ_STREAM_NAME,
        fields=fields,
        maxlen=settings.CELERY_DLQ_RETENTION_MAX_ENTRIES,
    )

    if event_id is None:
        logger.error(
            "dlq_write_failed",
            extra={"task_id": task_id, "task_name": task_name},
        )
        return False

    logger.warning(
        "task_written_to_dlq_stream",
        extra={
            "task_id": task_id,
            "task_name": task_name,
            "stream": settings.CELERY_DLQ_STREAM_NAME,
            "event_id": event_id,
            "exception_type": exception_type,
            "retry_count": retry_count,
            "trace_id": trace_id,
        },
    )
    return True


__all__ = ["write_to_dlq"]
