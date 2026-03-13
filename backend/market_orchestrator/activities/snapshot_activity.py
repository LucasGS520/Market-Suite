""" Activities Temporal para persistência de snapshot e limpeza do workflow """

from __future__ import annotations

import json
from datetime import timedelta

import structlog
from temporalio import activity

from market_orchestrator.schemas.schemas_snapshot import WorkflowSnapshot


logger = structlog.get_logger("orchestrator.activities.snapshot")

_SNAPSHOT_KEY = "workflow:snapshot:{monitored_id}"
_SNAPSHOT_TTL_SECONDS = 86400

@activity.defn(name="persist_workflow_snapshot")
async def persist_workflow_snapshot(snapshot: WorkflowSnapshot) -> None:
    """ Persiste o snapshot atual do workflow no Redis em modo best effort """
    try:
        from shared.utils.redis_client import get_redis_operational

        client = get_redis_operational()
        if client is None:
            return

        key = _SNAPSHOT_KEY.format(monitored_id=snapshot.monitored_id)
        data = {
            "state": snapshot.state.value
            if hasattr(snapshot.state, "value")
            else str(snapshot.state),
            "next_run_at": snapshot.next_run_at.isoformat()
            if snapshot.next_run_at
            else None,
            "last_run_at": snapshot.last_run_at.isoformat()
            if snapshot.last_run_at
            else None,
            "last_error": snapshot.last_error,
            "attempt_count": snapshot.attempt_count,
        }
        client.setex(key, timedelta(seconds=_SNAPSHOT_TTL_SECONDS), json.dumps(data))

    except Exception as exc:
        logger.warning("persist_workflow_snapshot_error", error=str(exc))

@activity.defn(name="cleanup_workflow_state")
async def cleanup_workflow_state(monitored_id: str) -> None:
    """ Remove marcadores transitórios de estado no Redis (idempotente) """
    try:
        from shared.utils.redis_client import get_redis_operational

        client = get_redis_operational()
        if client is None:
            return

        key = _SNAPSHOT_KEY.format(monitored_id=monitored_id)
        client.delete(key)

    except Exception as exc:
        logger.warning(
            "cleanup_workflow_state_error", monitored_id=monitored_id, error=str(exc)
        )
