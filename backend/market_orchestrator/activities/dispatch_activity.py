""" Activity Temporal para disparar uma coleta """

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from temporalio import activity


logger = structlog.get_logger("orchestrator.activities.dispatch")

#Prefixo da chave Redis que registra o timestamp do dispatch para correlação de status
_DISPATCH_KEY_PREFIX = "workflow:dispatch"
_DISPATCH_TTL_SECONDS = 7200  # 2h — tempo máximo esperado para conclusão de coleta

@activity.defn(name="dispatch_collection")
async def dispatch_collection(
    monitored_id: str,
    user_id: str,
    correlation_id: str,
    trace_id: str,
    force_compare: bool = False,
) -> bool:
    """ Enfileira a coleta usando o fluxo de Celery já existente.

    Persiste o timestamp de dispatch no Redis para que query_collection_status
    possa verificar se last_collected_at é posterior a este momento.
    """
    from temporalio.exceptions import ApplicationError

    #Propaga trace_id para o ContextVar — o processor structlog injeta automaticamente
    #em todos os logs subsequentes desta execução de activity
    try:
        from shared.utils.trace_context import set_trace_id as _set_trace_id
        _set_trace_id(trace_id)
    except Exception:
        pass

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

        #Salva timestamp de dispatch para correlação em query_collection_status
        try:
            from shared.utils.redis_client import get_redis_operational
            redis_client = get_redis_operational()
            if redis_client is not None:
                dispatch_key = f"{_DISPATCH_KEY_PREFIX}:{monitored_id}:{correlation_id}"
                dispatch_ts = datetime.now(timezone.utc).isoformat()
                redis_client.setex(dispatch_key, _DISPATCH_TTL_SECONDS, dispatch_ts)
        except Exception as redis_exc:
            #Redis inoperante não deve bloquear o enfileiramento
            logger.warning(
                "dispatch_collection_redis_store_failed",
                monitored_id=monitored_id,
                correlation_id=correlation_id,
                error=str(redis_exc),
            )

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
