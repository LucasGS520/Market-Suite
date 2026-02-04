""" Task de reconciliação da fila de prioridade de monitorados

Esta task garante que monitorados ativos e não pausados estejam presentes na
fila Redis, utilizando o ``next_check_at`` como referência de agendamento.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from shared.infra.db import SessionLocal
from market_alert.core.celery_app import celery_app
from market_alert.enums.enums_products import MonitoredStatus
from market_alert.models.models_products import MonitoredProduct
from market_alert.services.services_priority_queue_manager import enqueue_monitored_at


logger = structlog.get_logger("priority_queue_tasks")

def _utc_now() -> datetime:
    """ Retorna timestamp UTC sem microsegundos para consistência """
    return datetime.now(timezone.utc).replace(microsecond=0)

def _normalize_next_check(next_check_at: datetime | None, fallback: datetime) -> datetime:
    """ Normaliza o próximo check garantindo fuso UTC ou fallback imediato """
    if next_check_at is None:
        return fallback
    if next_check_at.tzinfo is None:
        return next_check_at.replace(tzinfo=timezone.utc)
    return next_check_at.astimezone(timezone.utc)

def _iter_active_monitored(db: Session) -> Iterable[tuple[UUID, datetime | None]]:
    """ Itera monitorados ativos que não estão pausados para reconciliação """
    return (
        db.query(MonitoredProduct.id, MonitoredProduct.next_check_at)
        .filter(
            MonitoredProduct.paused.is_(False),
            MonitoredProduct.status == MonitoredStatus.active,
        )
        .yield_per(500)
    )

@celery_app.task(name="market_alert.tasks.priority_queue_tasks.reconcile_priority_queue")
def reconcile_priority_queue() -> dict[str, int]:
    """ Recarrega a fila de prioridade com monitorados ativos """
    total = 0
    enqueued = 0
    failed = 0
    now = _utc_now()

    with SessionLocal() as db:
        for monitored_id, next_check_at in _iter_active_monitored(db):
            total += 1
            scheduled_at = _normalize_next_check(next_check_at, now)
            #Usamos enfileiramento individual para registrar ``enqueued_at`` de cada item
            if enqueue_monitored_at(monitored_id, scheduled_at, source="reconciliation"):
                enqueued += 1
            else:
                failed += 1

    logger.info(
        "priority_queue_reconciled",
        total=total,
        enqueued=enqueued,
        failed=failed,
    )
    return {"total": total, "enqueued": enqueued, "failed": failed}
