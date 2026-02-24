""" Task dedicada ao envio de notificações por canal.

Casca fina que delega toda a lógica de envio, retry e registro de tentativas
para services_notifications.process_notification().
"""

from __future__ import annotations

from uuid import UUID
import structlog

from shared.infra.db import SessionLocal

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.notifications.services_notifications import process_notification


logger = structlog.get_logger("notifications_send")

@celery_app.task(
    bind=True,
    max_retries=settings.NOTIFICATION_MAX_ATTEMPTS,
    soft_time_limit=30,
    time_limit=60,
    acks_late=True,
)
def send_notification_task(self, notification_id: str) -> None:
    """ Realiza o envio de uma notificação e delega controle de retry ao service layer """
    task_logger = logger.bind(task_id=self.request.id, notification_id=notification_id)

    with SessionLocal() as db:
        success = process_notification(db, notification_id=UUID(notification_id))

    if not success:
        task_logger.info(
            "notification_send_skipped_or_failed",
            notification_id=notification_id,
        )
