""" Reconciliação da fila de prioridade de coletas.

Garante que todos os monitorados ativos estejam presentes na fila Redis,
corrigindo perdas causadas por reinicializações de worker, falhas de Redis
ou race conditions durante o processamento contínuo.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from shared.utils.redis_client import get_redis_client

from market_continuous.queue.collection_queue import CollectionQueue

from market_alert.enums.enums_products import MonitoredStatus
from market_alert.models.models_products import MonitoredProduct



logger = logging.getLogger(__name__)

_RECONCILIATION_FLAG_KEY = "market_alert:collection:reconciliation:running"
_RECONCILIATION_FLAG_TTL_SECONDS = 5 * 60  # 5 minutos

def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)

def _normalize_next_check(next_check_at: datetime | None, fallback: datetime) -> datetime:
    if next_check_at is None:
        return fallback
    if next_check_at.tzinfo is None:
        return next_check_at.replace(tzinfo=timezone.utc)
    return next_check_at.astimezone(timezone.utc)

def _iter_active_monitored(db: Session) -> Iterable[tuple[UUID, datetime | None]]:
    return (
        db.query(MonitoredProduct.id, MonitoredProduct.next_check_at)
        .filter(
            MonitoredProduct.paused.is_(False),
            MonitoredProduct.status == MonitoredStatus.active,
        )
        .yield_per(500)
    )

def _acquire_reconciliation_flag() -> bool:
    client = get_redis_client()
    if client is None:
        logger.warning("reconciliation_flag_redis_unavailable")
        return True

    try:
        result = client.set(
            _RECONCILIATION_FLAG_KEY,
            "1",
            ex=_RECONCILIATION_FLAG_TTL_SECONDS,
            nx=True,
        )
        return result is not None
    except Exception as exc:
        logger.warning("reconciliation_flag_acquire_error: %s", exc)
        return True

def _release_reconciliation_flag() -> None:
    client = get_redis_client()
    if client is None:
        return
    try:
        client.delete(_RECONCILIATION_FLAG_KEY)
    except Exception as exc:
        logger.warning("reconciliation_flag_release_error: %s", exc)

def reconcile_collection_queue(
    db: Session,
    collection_queue: CollectionQueue | None = None,
) -> dict[str, int]:
    """ Recarrega a fila de prioridade com todos os monitorados ativos. """
    if not _acquire_reconciliation_flag():
        logger.info("reconciliation_skipped_already_running")
        return {"total": 0, "enqueued": 0, "failed": 0, "skipped": 1}

    queue = collection_queue or CollectionQueue()
    total = 0
    enqueued = 0
    failed = 0
    now = _utc_now()

    try:
        for monitored_id, next_check_at in _iter_active_monitored(db):
            total += 1
            scheduled_at = _normalize_next_check(next_check_at, now)

            status = queue.get_collection_status(monitored_id)
            if status != "not_found":
                continue

            if queue.enqueue_for_collection(monitored_id, scheduled_at, source="reconciliation"):
                enqueued += 1
            else:
                failed += 1

        logger.info("reconciliation_complete", total=total, enqueued=enqueued, failed=failed)
    except Exception as exc:
        logger.exception("reconciliation_error: %s", exc)
    finally:
        _release_reconciliation_flag()

    return {"total": total, "enqueued": enqueued, "failed": failed, "skipped": 0}


__all__ = ["reconcile_collection_queue"]
