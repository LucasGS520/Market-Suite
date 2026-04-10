""" Activity Temporal para consultar o status de conclusão da coleta. """
from __future__ import annotations

import json
from datetime import datetime, timezone

import structlog
from sqlalchemy import text
from temporalio import activity

from shared.schemas.shared_schemas_orchestrator import QueryStatusOutput


logger = structlog.get_logger("orchestrator.activities.status")

#Deve estar em sincronia com dispatch_activity._DISPATCH_KEY_PREFIX
_DISPATCH_KEY_PREFIX = "workflow:dispatch"

#Deve estar em sincronia com collector_product_task._COLLECTION_RESULT_KEY_PREFIX
_COLLECTION_RESULT_KEY_PREFIX = "workflow:collection_result"

# Outcomes que indicam conclusão bem-sucedida da coleta (sem erro de negócio)
_SUCCESSFUL_OUTCOMES = frozenset({"success", "not_modified"})

# Outcomes de lock transitório: coleta foi "absorvida" por outro worker — não é falha de produto
_LOCK_OUTCOMES = frozenset({"lock_skipped", "lock_exhausted"})


def _read_dispatch_timestamp(monitored_id: str, correlation_id: str) -> datetime | None:
    """ Lê o timestamp de dispatch armazenado pelo dispatch_collection no Redis."""
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


def _read_collection_result(monitored_id: str, correlation_id: str) -> dict | None:
    """ Lê o resultado de coleta sinalizado pelo collector_product_task no Redis.

    Retorna dict com ``{"outcome": str, "reason": str}`` ou None se ausente/erro.
    Presente apenas quando o collector terminou sua execução final (sem retry pendente).
    """
    try:
        from shared.utils.redis_client import get_redis_operational
        redis_client = get_redis_operational()
        if redis_client is None:
            return None
        result_key = f"{_COLLECTION_RESULT_KEY_PREFIX}:{monitored_id}:{correlation_id}"
        raw = redis_client.get(result_key)
        if raw is None:
            return None
        return json.loads(raw.decode())
    except Exception:
        return None


@activity.defn(name="query_collection_status")
async def query_collection_status(
    monitored_id: str,
    correlation_id: str,
) -> QueryStatusOutput:
    """ Consulta se a coleta do ciclo atual foi concluída.

    Estratégia em dois passos:
    1. Verifica chave Redis ``workflow:collection_result:{id}:{corr_id}`` sinalizada
       pelo collector_product_task ao terminar. Essa é a via rápida: detecta conclusão
       em segundos sem polling do banco.
    2. Fallback: compara ``last_scraped_at`` do monitorado com o timestamp de dispatch
       (via ``workflow:dispatch:{id}:{corr_id}``). Protege contra collectors antigos que
       não escrevem o result key.

    Semântica de outcomes para o workflow:
    - ``success`` / ``not_modified`` → completed=True, last_error=None (WaitingTimer)
    - ``lock_skipped`` / ``lock_exhausted`` → completed=True, last_error=None
      (lock é transitório — outro worker coletou; workflow vai para WaitingTimer)
    - ``no_result`` / ``error`` com reason → completed=True, last_error=reason (Backoff)
    """
    try:
        # --- Passo 1: verificar result key sinalizado pelo collector ---
        collection_result = _read_collection_result(monitored_id, correlation_id)
        if collection_result is not None:
            c_outcome = collection_result.get("outcome", "")
            c_reason = collection_result.get("reason", "")

            if c_outcome in _SUCCESSFUL_OUTCOMES:
                logger.info(
                    "query_collection_status_result_key_success",
                    monitored_id=monitored_id,
                    correlation_id=correlation_id,
                    outcome=c_outcome,
                )
                return QueryStatusOutput(completed=True)

            if c_reason in _LOCK_OUTCOMES or c_outcome == "no_result" and c_reason in _LOCK_OUTCOMES:
                # Lock transitório: não é falha do produto — workflow volta para WaitingTimer
                logger.info(
                    "query_collection_status_result_key_lock",
                    monitored_id=monitored_id,
                    correlation_id=correlation_id,
                    reason=c_reason,
                )
                return QueryStatusOutput(completed=True)

            # Falha real (no_result por parser, error por infra) → Backoff
            logger.info(
                "query_collection_status_result_key_failure",
                monitored_id=monitored_id,
                correlation_id=correlation_id,
                outcome=c_outcome,
                reason=c_reason,
            )
            return QueryStatusOutput(
                completed=True,
                last_error=c_reason or c_outcome or "collection_failed",
            )

        # --- Passo 2: fallback via last_scraped_at no banco ---
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
