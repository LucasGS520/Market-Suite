""" Activity Temporal para consultar o status de conclusão da coleta. """
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import text
from temporalio import activity

from shared.schemas.shared_schemas_orchestrator import QueryStatusOutput


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
) -> QueryStatusOutput:
    """ Consulta o banco para inferir se a coleta foi concluída.

    Compara last_scraped_at do monitorado com o timestamp de dispatch (lido do
    Redis via correlation_id) para garantir que apenas coletas posteriores ao
    dispatch corrente contam como conclusão.
    """
    try:
        from shared.infra.db.database import SessionLocal

        db = SessionLocal()
        try:
            row = db.execute(
                text(
                    "SELECT last_scraped_at FROM monitored_products "
                    "WHERE id = CAST(:id AS UUID)"
                ),
                {"id": monitored_id},
            ).fetchone()

            if row is None:
                return QueryStatusOutput(completed=True, last_error="monitored_not_found")

            last_scraped_at = row.last_scraped_at
            if last_scraped_at is None:
                return QueryStatusOutput(completed=False)

            dispatch_ts = _read_dispatch_timestamp(monitored_id, correlation_id)
            if dispatch_ts is None:
                #Redis indisponível ou chave expirou: aceita qualquer last_scraped_at
                #para evitar loop infinito após falha temporária de infra
                logger.warning(
                    "query_collection_status_dispatch_ts_missing",
                    monitored_id=monitored_id,
                    correlation_id=correlation_id,
                )
                return QueryStatusOutput(completed=True)

            #Normaliza timezone para comparação segura
            if last_scraped_at.tzinfo is None:
                last_scraped_at = last_scraped_at.replace(tzinfo=timezone.utc)

            completed = last_scraped_at >= dispatch_ts
            return QueryStatusOutput(completed=completed)

        finally:
            db.close()

    except Exception as exc:
        logger.warning(
            "query_collection_status_error",
            monitored_id=monitored_id,
            error=str(exc),
        )
        return QueryStatusOutput(completed=False, last_error=str(exc))
