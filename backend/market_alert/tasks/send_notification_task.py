""" Task dedicada ao envio de notificações por canal.

Casca fina que delega toda a lógica de envio, retry e registro de tentativas
para services_notifications.process_notification().
"""

from __future__ import annotations

from uuid import UUID
import structlog

from shared.infra.db import SessionLocal
from shared.utils.trace_context import set_trace_id

from market_alert.core.celery_app import celery_app
from market_alert.core.dlq_base_task import DLQTask
from market_alert.core.retry_policies import NOTIFICATION_RETRY
from market_alert.notifications.services_notifications import process_notification


logger = structlog.get_logger("notifications_send")

@celery_app.task(
    bind=True,
    base=DLQTask,
    **NOTIFICATION_RETRY,
)
def send_notification_task(self, notification_id: str) -> None:
    """ Realiza o envio de uma notificação e delega controle de retry ao service layer """
    set_trace_id(self.request.id or notification_id)
    task_logger = logger.bind(task_id=self.request.id, notification_id=notification_id)

    with SessionLocal() as db:
        success = process_notification(db, notification_id=UUID(notification_id))

    if not success:
        task_logger.info(
            "notification_send_skipped_or_failed",
            notification_id=notification_id,
        )
