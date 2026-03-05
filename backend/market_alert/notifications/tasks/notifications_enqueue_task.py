""" Task para enfileirar notificações pendentes """

from __future__ import annotations

import structlog

from shared.infra.db import SessionLocal
from shared.utils.trace_context import set_trace_id

from market_alert.infraestructure.celery.celery_app import celery_app
from market_alert.infraestructure.celery.retry_policies import ENQUEUE_RETRY
from market_alert.notifications.services.services_notifications import enqueue_pending_notifications


logger = structlog.get_logger("notifications_enqueue")

@celery_app.task(
    bind=True,
    **ENQUEUE_RETRY,
)
def enqueue_notifications_task(self, notification_ids: list[str] | None = None) -> int:
    """ Enfileira notificações pendentes para dispatch assíncrono.

    Casca fina que delega a busca de pendentes e o enfileiramento individual
    para ``services_notifications.enqueue_pending_notifications()``.
    """
    set_trace_id(self.request.id or "")
    with SessionLocal() as db:
        return enqueue_pending_notifications(
            db,
            notification_ids,
            trace_id=self.request.id,
        )
