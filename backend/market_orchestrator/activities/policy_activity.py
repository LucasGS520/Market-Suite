"""Activity Temporal para buscar a política atual do monitoramento."""
from __future__ import annotations

import structlog
from sqlalchemy import text
from temporalio import activity

from shared.scheduling import (
    SchedulingContext,
    calculate_schedule,
    EVENT_STANDARD,
)
from shared.schemas.shared_schemas_orchestrator import PolicyActivityOutput


logger = structlog.get_logger("orchestrator.activities.policy")

_FALLBACK_OUTPUT = PolicyActivityOutput(
    interval_seconds=3600,
    next_check_at=None,
    paused=False,
    stability_score=0,
    scheduling_reason="error_fallback",
)

@activity.defn(name="fetch_monitored_policy")
async def fetch_monitored_policy(monitored_id: str) -> PolicyActivityOutput:
    """Lê política/estado do monitorado no banco e computa o agendamento real.

    Retorna intervalo calculado pela lógica de estabilidade (shared.scheduling),
    sem fallback hardcoded de 3600s. Inclui stability_score e scheduling_reason
    para observabilidade no histórico Temporal.
    """
    try:
        from shared.infra.db.database import SessionLocal

        db = SessionLocal()
        try:
            row = db.execute(
                text(
                    "SELECT status, last_price_change_at, last_scraped_at, "
                    "group_collected_at, created_at, next_check_at, "
                    "stability_score, paused "
                    "FROM monitored_products WHERE id = CAST(:id AS UUID)"
                ),
                {"id": monitored_id},
            ).fetchone()

            if row is None:
                return PolicyActivityOutput(
                    interval_seconds=3600,
                    next_check_at=None,
                    paused=False,
                    stability_score=0,
                    scheduling_reason="product_not_found_fallback",
                )

            ctx = SchedulingContext(
                status=row.status if isinstance(row.status, str) else row.status.value,
                last_checked=None,
                last_price_change_at=row.last_price_change_at,
                group_collected_at=row.group_collected_at,
                last_scraped_at=row.last_scraped_at,
                created_at=row.created_at,
                next_check_at=row.next_check_at,
                stability_score=row.stability_score or 0,
            )
            decision = calculate_schedule(ctx, event_type=EVENT_STANDARD)

            return PolicyActivityOutput(
                interval_seconds=decision.interval_seconds,
                next_check_at=decision.next_check_at.isoformat(),
                paused=row.paused or False,
                stability_score=decision.stability_score,
                scheduling_reason=decision.reason,
            )
        finally:
            db.close()

    except Exception as exc:
        logger.warning(
            "fetch_monitored_policy_error", monitored_id=monitored_id, error=str(exc)
        )
        return _FALLBACK_OUTPUT
