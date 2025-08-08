""" Endpoint de verificação de saúde da aplicação """

import structlog
import redis
from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone

from infra.db import get_engine
from alert_app.core.config import settings


router = APIRouter(prefix="/health", tags=["Health"])
logger = structlog.get_logger("health_check")

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
    except SQLAlchemyError as e:
        logger.error("postgres_unavailable", errors=str(e))
        status["postgres"] = {"status": "error", "detail": str(e)}
        status["overall"] = "error"

    #Verificação do Redis
    redis_client = None
    try:
        redis_client = redis.from_url(settings.redis_url)
        redis_client.ping()
        status["redis"] = {"status": "ok"}
    except Exception as e:
        logger.error("redis_unavailable", error=str(e))
        status["redis"] = {"status": "error", "detail": str(e)}
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
    except Exception as e:
        logger.error("beat_check_failed", error=str(e))
        status["beat"] = {"status": "error", "detail": str(e)}
        status["overall"] = "error"

    logger.info("health_check_result", status=status)
    return status
