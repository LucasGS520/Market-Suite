""" Activity Temporal para disparar uma coleta """

from __future__ import annotations

from uuid import UUID

import structlog
from temporalio import activity


logger = structlog.get_logger("orchestrator.activities.dispatch")

@activity.defn(name="dispatch_collection")
async def dispatch_collection(
    monitored_id: str,
    user_id: str,
    correlation_id: str,
    trace_id: str,
    force_compare: bool = False,
) -> bool:
    """ Enfileira a coleta usando o fluxo de Celery já existente """
    from temporalio.exceptions import ApplicationError

    try:
        from market_alert.collectors.orchestrator.collector_service_orchestrator import enqueue_collect
        from market_alert.schemas.schemas_collection_payload import CollectionPayload

        payload = CollectionPayload(
            monitored_id=UUID(monitored_id),
            user_id=UUID(user_id),
            trace_id=trace_id,
            force_compare="true" if force_compare else None,
        )
        enqueue_collect(payload)
        logger.info(
            "dispatch_collection_ok",
            monitored_id=monitored_id,
            correlation_id=correlation_id,
            trace_id=trace_id,
        )
        return True

    except (ValueError, TypeError) as exc:
        raise ApplicationError(
            f"Payload inválido para dispatch_collection: {exc}",
            non_retryable=True,
        ) from exc
