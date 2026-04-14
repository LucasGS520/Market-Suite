""" Endpoint de verificação de saúde da aplicação """

import structlog
import redis
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from shared.infra.db import get_engine

from market_alert.core.config_alert import settings
from market_alert.infrastructure.redis_monitoring import get_redis_metrics


logger = structlog.get_logger("health_check")
router = APIRouter(prefix="/health", tags=["Health"])

@router.get("/", tags=["Health"])
def health_check():
    """ Endpoint para expor erros ou falhas de conexão """
    status = {"overall": "ok"}

    #Verificação do Postgres
    engine =  get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status["postgres"] = {"status": "ok"}
    except SQLAlchemyError:
        logger.exception("postgres_unavailable")
        status["postgres"] = {"status": "error", "detail": "Postgres indisponível"}
        status["overall"] = "error"

    #Verificação do Redis
    redis_client = None
    try:
        redis_client = redis.from_url(settings.redis_operational_url)
        redis_client.ping()
        status["redis"] = {"status": "ok"}
    except Exception:
        logger.exception("redis_unavailable")
        status["redis"] = {"status": "error", "detail": "Redis indisponível"}
        status["overall"] = "error"

    #Verificação do Beat (último sucesso)
    try:
        if redis_client is None:
            raise RuntimeError("Redis client not initialized")
        beat_last_success = redis_client.get("beat:last_success")
        if beat_last_success:
            ts = datetime.fromisoformat(beat_last_success.decode())
            now = datetime.now(timezone.utc)
            lag = (now - ts).total_seconds()
            beat_status = "ok" if lag < 300 else "stale" #5 minutos de tolerância
            status["beat"] = {
                "status": beat_status,
                "last_success": ts.isoformat(),
                "lag_seconds": int(lag)
            }
            if beat_status != "ok":
                status["overall"] = "error"
        else:
            status["beat"] = {"status": "missing"}
            status["overall"] = "error"
    except Exception:
        logger.exception("beat_check_failed")
        status["beat"] = {"status": "error", "detail": "Falha ao obter heartbeat"}
        status["overall"] = "error"

    #Métricas operacionais Redis + alertas antecipados de saturação
    try:
        redis_metrics = get_redis_metrics()
        status["redis_metrics"] = redis_metrics

        # DLQ com backlog indica tasks falhando permanentemente — degraded imediato
        dlq_backlog = redis_metrics.get("dlq_backlog")
        if dlq_backlog is not None and dlq_backlog > 0:
            status["overall"] = "degraded"
            status["coordination"] = {
                "status": "degraded",
                "detail": f"DLQ com {dlq_backlog} task(s) em falha permanente",
            }

        # Muitos workflows em WaitingResult pode indicar polling sem resolução (TMPRL1104)
        queue_processing = redis_metrics.get("queue_processing")
        if queue_processing is not None and queue_processing > 20:
            if status.get("overall") == "ok":
                status["overall"] = "degraded"
            coord = status.get("coordination", {})
            coord["queue_processing_high"] = queue_processing
            status["coordination"] = coord

        # Fila de scraping com backlog alto indica workers não conseguindo acompanhar dispatches
        scraping_depth = redis_metrics.get("celery_queue_scraping")
        if scraping_depth is not None and scraping_depth > 50:
            if status.get("overall") == "ok":
                status["overall"] = "degraded"
            coord = status.get("coordination", {})
            coord["scraping_queue_backlog"] = scraping_depth
            status["coordination"] = coord

    except Exception:
        logger.exception("redis_metrics_collection_failed")
        status["redis_metrics"] = None

    #Verificação de conectividade com o Temporal Server (não-bloqueante)
    try:
        from shared.clients.temporal.orchestrator_client import get_temporal_client
        temporal_ok = get_temporal_client().probe_connectivity_sync()
        status["temporal"] = {"status": "ok" if temporal_ok else "degraded"}
        if not temporal_ok and status["overall"] == "ok":
            status["overall"] = "degraded"
    except ImportError:
        status["temporal"] = {"status": "unavailable", "detail": "módulo não instalado"}
    except Exception:
        logger.exception("temporal_health_check_failed")
        status["temporal"] = {"status": "degraded", "detail": "Falha ao verificar Temporal"}

    logger.info("health_check_result", status=status)
    return status

@router.get("/temporal", tags=["Health"])
def temporal_health():
    """ Verifica conectividade com o Temporal Server.

    Retorna HTTP 200 com status=healthy quando conectado,
    HTTP 503 com status=unhealthy quando indisponível.
    """
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        from shared.clients.temporal.orchestrator_client import get_temporal_client, get_temporal_connection_info
        connected = get_temporal_client().probe_connectivity_sync()
        conn_info = get_temporal_connection_info()
        if connected:
            return {
                "status": "healthy",
                "temporal_connected": True,
                "namespace": conn_info["namespace"],
                "task_queue": conn_info["task_queue"],
                "last_check_at": checked_at,
            }
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "temporal_connected": False,
                "namespace": conn_info["namespace"],
                "task_queue": conn_info["task_queue"],
                "last_check_at": checked_at,
            },
        )
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "temporal_connected": False,
                "error": "módulo market_orchestrator não instalado",
                "last_check_at": checked_at,
            },
        )
    except Exception as exc:
        logger.exception("temporal_health_endpoint_failed")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "temporal_connected": False,
                "error": str(exc),
                "last_check_at": checked_at,
            },
        )

@router.get("/readiness", tags=["Health"])
def readiness_check():
    """ Valida se as dependências principais estão prontas para uso."""
    status = {"overall": "ok"}

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        status["postgres"] = {"status": "ok"}
    except SQLAlchemyError:
        logger.exception("readiness_postgres_unavailable")
        status["postgres"] = {"status": "error", "detail": "Postgres indisponível"}
        status["overall"] = "error"

    try:
        redis_client = redis.from_url(settings.redis_operational_url)
        redis_client.ping()
        status["redis"] = {"status": "ok"}
    except Exception:
        logger.exception("readiness_redis_unavailable")
        status["redis"] = {"status": "error", "detail": "Redis indisponível"}
        status["overall"] = "error"

    if status["overall"] != "ok":
        raise HTTPException(status_code=503, detail=status)

    return {"status": "ready", **status}
