""" Task para preparar notificações pendentes com retry e backoff """

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Iterable

import structlog

from shared.infra.db import SessionLocal

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.crud.crud_notifications import update_notification_status
from market_alert.enums.enums_notifications import NotificationStatus
from market_alert.models import Notification


logger = structlog.get_logger("notifications_enqueue")

def _calculate_next_attempt_at(
    attempts: int,
    *,
    reference: datetime,
) -> datetime:
    """ Calcula o próximo horário de tentativa usando backoff exponencial """
    base_delay = max(settings.NOTIFICATION_BACKOFF_BASE_SECONDS, 1)
    multiplier = max(settings.NOTIFICATION_BACKOFF_MULTIPLIER, 1)
    delay_seconds = base_delay * (multiplier ** max(attempts, 0))
    return reference + timedelta(seconds=delay_seconds)

def _filter_notifications(
    notifications: Iterable[Notification],
    *,
    now: datetime,
) -> list[Notification]:
    """ Filtra notificações elegíveis para novo enfileiramento """
    eligible: list[Notification] = []
    for notification in notifications:
        if notification.status not in {NotificationStatus.pending, NotificationStatus.failed}:
            continue
        if notification.attempts >= notification.max_attempts:
            continue
        if notification.next_attempt_at and notification.next_attempt_at > now:
            continue
        eligible.append(notification)
    return eligible

@celery_app.task(
    bind=True,
    max_retries=0,
    soft_time_limit=20,
    time_limit=40,
    acks_late=True,
)
def enqueue_notifications_task(self, notification_ids: list[str] | None = None) -> int:
    """ Atualiza notificações pendentes e calcula próximo retry quando necessário """
    task_logger = logger.bind(task_id=self.request.id)
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        query = db.query(Notification)
        if notification_ids:
            query = query.filter(Notification.id.in_(notification_ids))
        else:
            query = query.filter(Notification.status.in_([NotificationStatus.pending, NotificationStatus.failed]))

        notifications = _filter_notifications(query.all(), now=now)
        for notification in notifications:
            next_attempt_at = notification.next_attempt_at or _calculate_next_attempt_at(
                notification.attempts,
                reference=now,
            )
            update_notification_status(
                db,
                notification=notification,
                status=notification.status,
                next_attempt_at=next_attempt_at,
                commit=False,
            )

        db.commit()

    task_logger.info(
        "notifications_enqueued",
        count=len(notifications),
        notification_ids=notification_ids,
    )
    return len(notifications)
        