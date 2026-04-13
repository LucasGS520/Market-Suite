""" Activity Temporal para consultar o status de conclusão da coleta. """
from __future__ import annotations

import json
from datetime import datetime, timezone

import structlog
from sqlalchemy import text
from temporalio import activity

from shared.schemas.shared_schemas_orchestrator import QueryStatusOutput
from shared.schemas.collection_catalog import (
    SUCCESSFUL_OUTCOMES,
    NEUTRAL_REASONS,
    get_error_class,
    has_source_integrity,
)


logger = structlog.get_logger("orchestrator.activities.status")

#Deve estar em sincronia com dispatch_activity._DISPATCH_KEY_PREFIX
_DISPATCH_KEY_PREFIX = "workflow:dispatch"

#Deve estar em sincronia com collector_product_task._COLLECTION_RESULT_KEY_PREFIX
_COLLECTION_RESULT_KEY_PREFIX = "workflow:collection_result"


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

    Semântica de outcomes para o workflow (via collection_catalog):
    - ``success`` / ``not_modified`` → completed=True, last_error=None (WaitingTimer)
    - reason em NEUTRAL_REASONS (lock_skipped, paused, scraping_suspended, missing_target,
      ignored_due_to_inactive) → completed=True, last_error=None (WaitingTimer)
    - ``error`` / ``no_result`` com reason não-neutro → completed=True, last_error=reason
      + error_class (transient/structural/domain_empty) para observabilidade (Backoff)
    """
    try:
        # --- Passo 1: verificar result key sinalizado pelo collector ---
        collection_result = _read_collection_result(monitored_id, correlation_id)
        if collection_result is not None:
            c_outcome = collection_result.get("outcome", "")
            c_reason = collection_result.get("reason") or None

            #Sucesso confiável: dados coletados com integridade
            if c_outcome in SUCCESSFUL_OUTCOMES:
                logger.info(
                    "query_collection_status_result_key_success",
                    monitored_id=monitored_id,
                    correlation_id=correlation_id,
                    outcome=c_outcome,
                    source_integrity=has_source_integrity(c_outcome, c_reason),
                )
                return QueryStatusOutput(
                    completed=True,
                    outcome=c_outcome,
                )

            #Neutral: lock, pausa, inativo, suspended, missing_target
            #Não é falha do produto — workflow retorna para WaitingTimer sem backoff
            if c_reason in NEUTRAL_REASONS:
                logger.info(
                    "query_collection_status_result_key_neutral",
                    monitored_id=monitored_id,
                    correlation_id=correlation_id,
                    outcome=c_outcome,
                    reason=c_reason,
                    semantic_category=get_error_class(c_reason),
                    source_integrity=has_source_integrity(c_outcome, c_reason),
                )
                return QueryStatusOutput(
                    completed=True,
                    outcome=c_outcome,
                )

            #Falha tipada (error transitório/estrutural ou no_result sem parse íntegro)
            #last_error preenchido → workflow vai para Backoff
            c_error_class = get_error_class(c_reason)
            logger.info(
                "query_collection_status_result_key_failure",
                monitored_id=monitored_id,
                correlation_id=correlation_id,
                outcome=c_outcome,
                reason=c_reason,
                error_class=c_error_class,
                semantic_category=c_error_class,
                source_integrity=has_source_integrity(c_outcome, c_reason),
            )
            return QueryStatusOutput(
                completed=True,
                last_error=c_reason or c_outcome or "collection_failed",
                outcome=c_outcome,
                error_class=c_error_class,
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
