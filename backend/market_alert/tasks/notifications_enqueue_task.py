""" Task para enfileirar e despachar notificações pendentes """

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import time
from typing import Iterable
from uuid import UUID

import structlog

from shared.infra.db import SessionLocal
from shared.metrics.metrics_notifications import (
    NOTIFICATION_ATTEMPTS_TOTAL,
    NOTIFICATION_DISPATCH_TOTAL,
)

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.crud.crud_notifications import (
    acquire_notification_for_processing,
    add_notification_attempt,
    get_pending_notifications,
    mark_notification_failed,
    mark_notification_sent,
)
from market_alert.enums.enums_notifications import DeliveryStatus, NotificationStatus
from market_alert.models import Notification
from market_alert.notifications.channels import get_channel_adapter


logger = structlog.get_logger("notifications_enqueue")

def _calculate_next_attempt_at(
    attempts: int,
    *,
    reference: datetime,
) -> datetime:
    """ Calcula o próximo horário de tentativa usando backoff exponencial """
    base_delay = max(settings.NOTIFICATION_BACKOFF_BASE_SECONDS, 1)
    multiplier = max(settings.NOTIFICATION_BACKOFF_MULTIPLIER, 1)
    delay_seconds = base_delay * (multiplier ** max(attempts - 1, 0))
    return reference + timedelta(seconds=delay_seconds)

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

@celery_app.task(
    bind=True,
    max_retries=settings.NOTIFICATION_MAX_ATTEMPTS,
    soft_time_limit=30,
    time_limit=60,
    acks_late=True,
)
def send_notification_task(self, notification_id: str) -> None:
    """ Realiza o envio de uma notificação e controla retries """
    task_logger = logger.bind(task_id=self.request.id, notification_id=notification_id)
    start = time.perf_counter()

    with SessionLocal() as db:
        with db.begin():
            notification = acquire_notification_for_processing(
                db,
                notification_id=UUID(notification_id),
            )
            if notification is None:
                task_logger.info(
                    "notification_processing_skipped",
                    reason="not_found_or_locked",
                )
                return
            
        adapter = get_channel_adapter(notification.channel)
        payload = {
            "recipient": notification.recipient,
            "subject": notification.subject,
            "message": notification.message,
            "channel": notification.channel.value,
            "payload": notification.payload or {},
        }

        success = False
        response: dict | None = None
        error_code: str | None = None
        error_message: str | None = None

        try:
            success, response, error_code = adapter.send(payload)
        except Exception as exc:
            success = False
            error_message = str(exc)
            error_code = "adapter_exception"

        latency_ms = int((time.perf_counter() - start) * 1000)
        status = DeliveryStatus.success if success else DeliveryStatus.failed

        with db.begin():
            add_notification_attempt(
                db,
                notification_id=notification.id,
                attempt_number=notification.attempts,
                status=status,
                provider_response=response,
                error_code=error_code,
                error_message=error_message,
                latency_ms=latency_ms,
                attempted_at=datetime.now(timezone.utc),
                commit=False,
            )

            if success:
                mark_notification_sent(
                    db,
                    notification=notification,
                    event_type=notification.event_log.event_type,
                    cooldown_seconds=notification.cooldown_seconds,
                    commit=False,
                )
                NOTIFICATION_DISPATCH_TOTAL.labels(
                    channel=notification.channel.value,
                    status=NotificationStatus.sent.value,
                ).inc()
                NOTIFICATION_ATTEMPTS_TOTAL.labels(
                    channel=notification.channel.value,
                    outcome="success",
                ).inc()
                task_logger.info(
                    "notification_sent",
                    channel=notification.channel.value,
                )
                return
                
            next_attempt_at = _calculate_next_attempt_at(
                notification.attempts,
                reference=datetime.now(timezone.utc),
            )
            mark_notification_failed(
                db,
                notification=notification,
                next_attempt_at=next_attempt_at,
                commit=False,
            )
            NOTIFICATION_DISPATCH_TOTAL.labels(
                channel=notification.channel.value,
                status=NotificationStatus.failed.value,
            ).inc()
            NOTIFICATION_ATTEMPTS_TOTAL.labels(
                channel=notification.channel.value,
                outcome="failed",
            ).inc()

        if notification.attempts >= notification.max_attempts:
            task_logger.warning(
                "notification_failed_max_attempts",
                channel=notification.channel.value,
            )
            return

        countdown = int((next_attempt_at - datetime.now(timezone.utc)).total_seconds())
        task_logger.warning(
            "notification_send_failed",
            channel=notification.channel.value,
            error_code=error_code,
            error_message=error_message,
        )
        raise self.retry(countdown=max(countdown, 1))
        