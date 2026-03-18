""" Endpoint de verificação de saúde da aplicação """

import structlog
import redis
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from shared.infra.db import get_engine
from market_alert.core.config_alert import settings
from market_alert.infraestructure.redis_monitoring import get_redis_metrics


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

    #Métricas operacionais Redis
    try:
        status["redis_metrics"] = get_redis_metrics()
    except Exception:
        logger.exception("redis_metrics_collection_failed")
        status["redis_metrics"] = None

    #Verificação de conectividade com o Temporal Server (não-bloqueante)
    try:
        from market_orchestrator.alert.alert_client import get_temporal_client
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

    Retorna status e timestamp da verificação. Nunca lança exceção —
    indisponibilidade do Temporal é reportada como degraded, não como erro HTTP.
    """
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        from market_orchestrator.alert.alert_client import get_temporal_client
        connected = get_temporal_client().probe_connectivity_sync()
        return {
            "temporal_connected": connected,
            "last_check_at": checked_at,
        }
    except ImportError:
        return {
            "temporal_connected": False,
            "last_check_at": checked_at,
            "detail": "módulo market_orchestrator não instalado",
        }
    except Exception:
        logger.exception("temporal_health_endpoint_failed")
        return {
            "temporal_connected": False,
            "last_check_at": checked_at,
            "detail": "falha ao verificar Temporal",
        }

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
