""" Activity Temporal para buscar a política atual do monitoramento """

from __future__ import annotations

from uuid import UUID

import structlog
from temporalio import activity


logger = structlog.get_logger("orchestrator.activities.policy")

@activity.defn(name="fetch_monitored_policy")
async def fetch_monitored_policy(monitored_id: str) -> dict:
    """ Lê política/estado do monitor no banco de negócio para uso determinístico no workflow """
    try:
        from shared.infra.db.database import SessionLocal
        from market_alert.products.crud.crud_monitored import get_monitored_product_by_id

        db = SessionLocal()
        try:
            monitored = get_monitored_product_by_id(db, UUID(monitored_id))
            if monitored is None:
                return {"interval_seconds": 3600, "next_check_at": None, "paused": False}

            interval = getattr(monitored, "check_interval", 3600) or 3600
            next_check_at = getattr(monitored, "next_check_at", None)
            paused = getattr(monitored, "paused", False) or False

            return {
                "interval_seconds": interval,
                "next_check_at": next_check_at.isoformat() if next_check_at else None,
                "paused": paused,
            }
        finally:
            db.close()

    except Exception as exc:
        logger.warning(
            "fetch_monitored_policy_error", monitored_id=monitored_id, error=str(exc)
        )
        return {"interval_seconds": 3600, "next_check_at": None, "paused": False}
