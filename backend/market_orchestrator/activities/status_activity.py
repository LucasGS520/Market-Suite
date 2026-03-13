"""Activity Temporal para consultar o status de conclusão da coleta."""

from __future__ import annotations

from uuid import UUID

import structlog
from temporalio import activity

from market_orchestrator.schemas.schemas_snapshot import CollectionStatusResult


logger = structlog.get_logger("orchestrator.activities.status")

@activity.defn(name="query_collection_status")
async def query_collection_status(
    monitored_id: str,
    correlation_id: str,
) -> CollectionStatusResult:
    """ Consulta o banco de negócio para inferir se a coleta foi concluída """
    try:
        from shared.infra.db.database import SessionLocal
        from market_alert.products.crud.crud_monitored import get_monitored_product_by_id

        db = SessionLocal()
        try:
            monitored = get_monitored_product_by_id(db, UUID(monitored_id))
            if monitored is None:
                return CollectionStatusResult(
                    completed=True, last_error="monitored_not_found"
                )

            completed = monitored.last_collected_at is not None
            return CollectionStatusResult(completed=completed)
        finally:
            db.close()

    except Exception as exc:
        logger.warning(
            "query_collection_status_error",
            monitored_id=monitored_id,
            error=str(exc),
        )
        return CollectionStatusResult(completed=False, last_error=str(exc))
