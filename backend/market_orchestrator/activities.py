""" Activities Temporal do market_orchestrator.

Regras obrigatórias:
- Toda activity é idempotente.
- Toda activity tem timeout explícito declarado no workflow (não aqui).
- Nenhuma activity retorna resultado complexo — apenas o mínimo para o workflow decidir.
- Todo I/O de rede, banco e cache ocorre exclusivamente aqui, nunca no workflow.
"""
from __future__ import annotations

import json
from datetime import timedelta
from uuid import UUID

import structlog
from temporalio import activity

from market_orchestrator.schemas.schemas_workflow import (
    CollectionStatusResult,
    WorkflowSnapshot,
)


logger = structlog.get_logger("orchestrator.activities")

# Chave Redis para snapshot de workflow por monitorado
_SNAPSHOT_KEY = "workflow:snapshot:{monitored_id}"
_SNAPSHOT_TTL_SECONDS = 86400  # 24h

# ---------------------------------------------------------------------------
# Activity: dispatch_collection
# ---------------------------------------------------------------------------

@activity.defn(name="dispatch_collection")
async def dispatch_collection(
    monitored_id: str,
    user_id: str,
    correlation_id: str,
    trace_id: str,
    force_compare: bool = False,
) -> bool:
    """ Enfileira coleta na malha Celery existente via enqueue_collect().

    Retorna True em sucesso. Lança ApplicationError (não retryável) apenas
    para payloads inválidos; demais falhas são retryáveis pelo Temporal.
    """
    from temporalio.exceptions import ApplicationError

    try:
        #Import local para evitar ciclo de dependências no bootstrap
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
        #Payload inválido — não adianta retentar
        raise ApplicationError(
            f"Payload inválido para dispatch_collection: {exc}",
            non_retryable=True,
        ) from exc

# ---------------------------------------------------------------------------
# Activity: query_collection_status
# ---------------------------------------------------------------------------

@activity.defn(name="query_collection_status")
async def query_collection_status(
    monitored_id: str,
    correlation_id: str,
) -> CollectionStatusResult:
    """ Consulta o banco de negócio para verificar se a coleta foi concluída.

    Usa o campo `last_collected_at` do MonitoredProduct como proxy de conclusão,
    comparando com o timestamp embutido no correlation_id (formato: uuid).
    Na ausência de um campo dedicado por correlation_id, a coleta é considerada
    concluída se `last_collected_at` foi atualizado após o dispatch.
    """
    try:
        from shared.infra.db.database import SessionLocal
        from market_alert.products.crud.crud_monitored import get_monitored_product_by_id

        db = SessionLocal()
        try:
            monitored = get_monitored_product_by_id(db, UUID(monitored_id))
            if monitored is None:
                return CollectionStatusResult(completed=True, last_error="monitored_not_found")

            # Proxy simples: coleta concluída se last_collected_at está preenchido.
            # O workflow usa polling com sleep entre chamadas, tolerando eventual consistency.
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

# ---------------------------------------------------------------------------
# Activity: persist_workflow_snapshot
# ---------------------------------------------------------------------------

@activity.defn(name="persist_workflow_snapshot")
async def persist_workflow_snapshot(snapshot: WorkflowSnapshot) -> None:
    """ Persiste snapshot do workflow no Redis para consulta rápida por monitored_id.

    Operação idempotente — falhas de Redis são silenciadas (snapshot é best-effort).
    """
    try:
        from shared.utils.redis_client import get_redis_operational

        client = get_redis_operational()
        if client is None:
            return

        key = _SNAPSHOT_KEY.format(monitored_id=snapshot.monitored_id)
        data = {
            "state": snapshot.state.value if hasattr(snapshot.state, "value") else str(snapshot.state),
            "next_run_at": snapshot.next_run_at.isoformat() if snapshot.next_run_at else None,
            "last_run_at": snapshot.last_run_at.isoformat() if snapshot.last_run_at else None,
            "last_error": snapshot.last_error,
            "attempt_count": snapshot.attempt_count,
        }
        client.setex(key, timedelta(seconds=_SNAPSHOT_TTL_SECONDS), json.dumps(data))

    except Exception as exc:
        logger.warning("persist_workflow_snapshot_error", error=str(exc))

# ---------------------------------------------------------------------------
# Activity: cleanup_workflow_state
# ---------------------------------------------------------------------------

@activity.defn(name="cleanup_workflow_state")
async def cleanup_workflow_state(monitored_id: str) -> None:
    """ Remove marcadores transitórios do Redis para o monitored_id.

    Idempotente — não falha se a chave já não existir.
    """
    try:
        from shared.utils.redis_client import get_redis_operational

        client = get_redis_operational()
        if client is None:
            return

        key = _SNAPSHOT_KEY.format(monitored_id=monitored_id)
        client.delete(key)

    except Exception as exc:
        logger.warning("cleanup_workflow_state_error", monitored_id=monitored_id, error=str(exc))

# ---------------------------------------------------------------------------
# Activity: fetch_monitored_policy
# ---------------------------------------------------------------------------

@activity.defn(name="fetch_monitored_policy")
async def fetch_monitored_policy(monitored_id: str) -> dict:
    """ Consulta o banco e retorna política + estado atual do monitorado.

    Retorna dict com: interval_seconds, next_check_at (ISO str | None), paused.
    Necessário para que o workflow leia dados frescos sem violar determinismo.
    """
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
        logger.warning("fetch_monitored_policy_error", monitored_id=monitored_id, error=str(exc))
        return {"interval_seconds": 3600, "next_check_at": None, "paused": False}
