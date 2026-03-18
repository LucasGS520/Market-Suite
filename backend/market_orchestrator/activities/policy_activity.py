""" Activity Temporal para buscar a política atual do monitoramento """

from __future__ import annotations

from uuid import UUID

import structlog
from temporalio import activity

from shared.scheduling import (
    SchedulingContext,
    calculate_schedule,
    EVENT_STANDARD,
)


logger = structlog.get_logger("orchestrator.activities.policy")

@activity.defn(name="fetch_monitored_policy")
async def fetch_monitored_policy(monitored_id: str) -> dict:
    """ Lê política/estado do monitor no banco e computa o agendamento real.

    Retorna intervalo calculado pela lógica de estabilidade (shared.scheduling),
    eliminando o fallback hardcoded de 3600s. Inclui ``stability_score`` e
    ``scheduling_reason`` para observabilidade no histórico Temporal.
    """
    try:
        from shared.infra.db.database import SessionLocal
        from market_alert.products.crud.crud_monitored import get_monitored_product_by_id

        db = SessionLocal()
        try:
            monitored = get_monitored_product_by_id(db, UUID(monitored_id))
            if monitored is None:
                return {
                    "interval_seconds": 3600,
                    "next_check_at": None,
                    "paused": False,
                    "stability_score": 0,
                    "scheduling_reason": "product_not_found_fallback",
                }

            ctx = SchedulingContext(
                status=monitored.status.value,
                last_checked=getattr(monitored, "last_checked", None),
                last_price_change_at=monitored.last_price_change_at,
                group_collected_at=monitored.group_collected_at,
                last_scraped_at=monitored.last_scraped_at,
                created_at=monitored.created_at,
                next_check_at=monitored.next_check_at,
                stability_score=getattr(monitored, "stability_score", 0) or 0,
            )
            decision = calculate_schedule(ctx, event_type=EVENT_STANDARD)

            return {
                "interval_seconds": decision.interval_seconds,
                "next_check_at": decision.next_check_at.isoformat(),
                "paused": monitored.paused or False,
                "stability_score": decision.stability_score,
                "scheduling_reason": decision.reason,
            }
        finally:
            db.close()

    except Exception as exc:
        logger.warning(
            "fetch_monitored_policy_error", monitored_id=monitored_id, error=str(exc)
        )
        return {
            "interval_seconds": 3600,
            "next_check_at": None,
            "paused": False,
            "stability_score": 0,
            "scheduling_reason": "error_fallback",
        }
