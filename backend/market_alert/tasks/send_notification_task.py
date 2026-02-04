""" Task dedicada ao envio de notificações por canal """

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import time
from uuid import UUID

import structlog

from shared.infra.db import SessionLocal
from shared.utils.redis_locks import acquire_notification_lock, release_notification_lock

from market_alert.core.celery_app import celery_app
from market_alert.core.config_alert import settings
from market_alert.crud.crud_notifications import (
    acquire_notification_for_processing,
    add_notification_attempt,
    mark_notification_dead_letter,
    mark_notification_failed,
    mark_notification_sent,
)
from market_alert.enums.enums_notifications import DeliveryStatus
from market_alert.notifications.channels import get_channel_adapter


logger = structlog.get_logger("notifications_send")
_RETRY_SCHEDULE_SECONDS = {1: 60, 2: 300}

def _calculate_next_attempt(attempts: int, *, now: datetime) -> datetime | None:
    """ Calcula o próximo instante com base no backoff exigido """
    delay = _RETRY_SCHEDULE_SECONDS.get(attempts)
    if delay is None:
        return None
    return now + timedelta(seconds=delay)

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
            
        lock_acquired, lock_owner = acquire_notification_lock(notification.dedup_hash, ttl_seconds=60)
        if not lock_acquired:
            task_logger.info(
                "notification_processing_skipped",
                reason="send_lock_unavailable",
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

        result: dict[str, object] = {}
        try:
            result = adapter.send(payload)
        except Exception as exc:
            result = {"success": False, "error": "adapter_exception", "raw_response": {"detail": str(exc)}}

        success = bool(result.get("success"))
        provider_message_id = result.get("provider_id")
        error_code = result.get("error") if not success else None
        error_message = None
        if not success and isinstance(result.get("raw_response"), dict):
            error_message = result["raw_response"].get("detail")

        latency_seconds = time.perf_counter() - start
        latency_ms = int(latency_seconds * 1000)
        status = DeliveryStatus.success if success else DeliveryStatus.failed

        with db.begin():
            add_notification_attempt(
                db,
                notification=notification,
                event_type=notification.event_log.event_type,
                cooldown_seconds=notification.cooldown_seconds,
                commit=False,
            )
            task_logger.info("notification_sent", channel=notification.channel.value)
            release_notification_lock(notification.dedup_hash, lock_owner)
            return
        
        next_attempt_at = _calculate_next_attempt(
            notification.attempts,
            now=datetime.now(timezone.utc),
        )
        mark_notification_failed(
            db,
            notification=notification,
            next_attempt_at=next_attempt_at,
            commit=False,
        )

    if notification.attempts >= notification.max_attempts or next_attempt_at is None:
        with db.begin():
            mark_notification_dead_letter(db, notification=notification, commit=False)
        task_logger.warning("notification_dead_lettered", channel=notification.channel.value)
        release_notification_lock(notification.dedup_hash, lock_owner)
        return
    
    countdown = int((next_attempt_at - datetime.now(timezone.utc)).total_seconds())
    task_logger.warning(
        "notification_send_failed",
        channel=notification.channel.value,
        error_code=error_code,
    )
    release_notification_lock(notification.dedup_hash, lock_owner)
    raise self.retry(countdown=max(countdown, 1))
