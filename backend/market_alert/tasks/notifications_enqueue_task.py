""" Task para enfileirar notificações pendentes """

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

import structlog

from shared.infra.db import SessionLocal

from market_alert.core.celery_app import celery_app
from market_alert.crud.crud_notifications import get_pending_notifications
from market_alert.models import Notification
from market_alert.tasks.send_notification_task import send_notification_task


logger = structlog.get_logger("notifications_enqueue")

def _enqueue_notifications(
    notifications: Iterable[Notification],
) -> int:
    """ Dispara tasks de envio para as notificações informadas """
    count = 0
    for notification in notifications:
        send_notification_task.apply_async(
            args=[str(notification.id)],
            queue="notifications",
        )
        count += 1
    return count

@celery_app.task(
    bind=True,
    max_retries=0,
    soft_time_limit=20,
    time_limit=40,
    acks_late=True,
)
def enqueue_notifications_task(self, notification_ids: list[str] | None = None) -> int:
    """ Enfileira notificações pendentes para dispatch assíncrono """
    task_logger = logger.bind(task_id=self.request.id)
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        ids = [UUID(value) for value in notification_ids] if notification_ids else None
        pending = get_pending_notifications(
            db,
            limit=200,
            now=now,
            notification_ids=ids,
        )
        total = _enqueue_notifications(pending)

    task_logger.info(
        "notifications_enqueued",
        count=total,
        notification_ids=notification_ids,
    )
    return total
        