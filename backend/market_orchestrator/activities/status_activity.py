"""Activity Temporal para consultar o status de conclusão da coleta."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from temporalio import activity

from market_orchestrator.schemas.schemas_snapshot import CollectionStatusResult


logger = structlog.get_logger("orchestrator.activities.status")

#Deve estar em sincronia com dispatch_activity._DISPATCH_KEY_PREFIX
_DISPATCH_KEY_PREFIX = "workflow:dispatch"

def _read_dispatch_timestamp(monitored_id: str, correlation_id: str) -> datetime | None:
    """ Lê o timestamp de dispatch armazenado pelo dispatch_collection no Redis.

    Retorna None se Redis estiver indisponível ou a chave expirou.
    """
    try:
        from shared.utils.redis_client import get_redis_operational
        redis_client = get_redis_operational()
        if redis_client is None:
            return None
        dispatch_key = f"{_DISPATCH_KEY_PREFIX}:{monitored_id}:{correlation_id}"
        raw = redis_client.get(dispatch_key)
        if raw is None:
            return None
        return datetime.fromisoformat(raw.decode())
    except Exception:
        return None

@activity.defn(name="query_collection_status")
async def query_collection_status(
    monitored_id: str,
    correlation_id: str,
) -> CollectionStatusResult:
    """ Consulta o banco de negócio para inferir se a coleta foi concluída.

    Compara last_collected_at do monitorado com o timestamp de dispatch (lido do
    Redis via correlation_id) para garantir que apenas coletas posteriores ao
    dispatch corrente contam como conclusão.
    """
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

            last_collected_at = monitored.last_collected_at
            if last_collected_at is None:
                return CollectionStatusResult(completed=False)

            dispatch_ts = _read_dispatch_timestamp(monitored_id, correlation_id)
            if dispatch_ts is None:
                #Redis indisponível ou chave expirou: aceita qualquer last_collected_at
                #para evitar loop infinito após falha temporária de infra
                logger.warning(
                    "query_collection_status_dispatch_ts_missing",
                    monitored_id=monitored_id,
                    correlation_id=correlation_id,
                )
                return CollectionStatusResult(completed=True)

            #Normaliza timezone para comparação segura
            if last_collected_at.tzinfo is None:
                last_collected_at = last_collected_at.replace(tzinfo=timezone.utc)

            completed = last_collected_at >= dispatch_ts
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
