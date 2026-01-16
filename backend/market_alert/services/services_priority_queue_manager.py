""" Serviços de apoio para operar a fila contínua de monitorados """

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog

from shared.metrics.metrics_priority_queue import (
    PRIORITY_QUEUE_ENQUEUED_TOTAL,
    PRIORITY_QUEUE_FALLBACK_TOTAL,
)
from market_alert.services.services_priority_queue import PriorityQueueService


logger = structlog.get_logger("priority_queue_manager")

def _utc_now() -> datetime:
    """ Retorna timestamp UTC sem microssegundos para consistência de métricas """
    return datetime.now(timezone.utc).replace(microsecond=0)

def enqueue_monitored_now(
    monitored_id: UUID,
    *,
    source: str,
    queue_service: PriorityQueueService | None = None,
) -> bool:
    """ Enfileira um monitorado com prioridade máxima na fila contínua """
    service = queue_service or PriorityQueueService()
    enqueued_at = _utc_now()
    if not service.enqueue_now(str(monitored_id)):
        PRIORITY_QUEUE_FALLBACK_TOTAL.labels(source=source).inc()
        logger.warning(
            "priority_queue_enqueue_failed",
            monitored_id=str(monitored_id),
            source=source,
        )
        return False
    
    service.set_enqueued_at(str(monitored_id), enqueued_at)
    PRIORITY_QUEUE_ENQUEUED_TOTAL.labels(source=source).inc()
    logger.info(
        "priority_queue_enqueued",
        monitored_id=str(monitored_id),
        source=source,
        enqueued_at=enqueued_at.isoformat(),
    )
    return True

def enqueue_monitored_at(
    monitored_id: UUID,
    scheduled_at: datetime,
    *,
    source: str,
    queue_service: PriorityQueueService | None = None,
) -> bool:
    """ Enfileira um monitorado com horário programado """
    service = queue_service or PriorityQueueService()
    normalized_time = scheduled_at
    if normalized_time.tzinfo is None:
        normalized_time = normalized_time.replace(tzinfo=timezone.utc)

    enqueued_at = _utc_now()
    if not service.enqueue(str(monitored_id), normalized_time):
        PRIORITY_QUEUE_FALLBACK_TOTAL.labels(source=source).inc()
        logger.warning(
            "priority_queue_schedule_failed",
            monitored_id=str(monitored_id),
            source=source,
            scheduled_at=normalized_time.isoformat(),
        )
        return False
    
    service.set_enqueued_at(str(monitored_id), enqueued_at)
    PRIORITY_QUEUE_ENQUEUED_TOTAL.labels(source=source).inc()
    logger.info(
        "priority_queue_scheduled",
        monitored_id=str(monitored_id),
        source=source,
        enqueued_at=enqueued_at.isoformat(),
        scheduled_at=normalized_time.isoformat(),
    )
    return True

def remove_monitored_from_priority_queue(
    product_id: UUID,
    *,
    source: str,
    queue_service: PriorityQueueService | None = None,
) -> bool:
    """ Remove um item da fila de prioridade para pausas ou exclusões """
    service = queue_service or PriorityQueueService()
    removed = service.remove(str(product_id))
    if removed:
        logger.info(
            "priority_queue_removed",
            product_id=str(product_id),
            source=source,
        )
    else:
        logger.warning(
            "priority_queue_remove_failed",
            product_id=str(product_id),
            source=source,
        )
    return removed
