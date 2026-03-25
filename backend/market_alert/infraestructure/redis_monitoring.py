""" Métricas operacionais do Redis para monitoramento e alertas.

Expõe snapshot das métricas críticas de saúde do Redis, cobrindo:
- Uso de memória
- Tamanho de chaves por DB
- Backlog da DLQ (stream Celery)
- Filas operacionais (priority_queue e processing)

Uso::

    from market_alert.infraestructure.redis_monitoring import get_redis_metrics

    metrics = get_redis_metrics()
    # metrics["memory_used_human"] → "42.5M"
    # metrics["dlq_backlog"] → 0
    # metrics["queue_pending"] → 15

Degradação segura: todas as métricas retornam None em caso de falha no Redis,
permitindo que o endpoint de health continue respondendo sem lançar exceção.
"""

from __future__ import annotations

import structlog

from shared.utils.redis_client import get_redis_operational
from market_alert.core.config_alert import settings


logger = structlog.get_logger("redis_monitoring")

def get_redis_metrics() -> dict:
    """ Coleta métricas operacionais do Redis.

    Returns:
        Dicionário com métricas de memória, filas e DLQ. Valores ausentes
        são representados como None para diferenciar de "zero".
    """
    client = get_redis_operational()
    if client is None:
        logger.warning("redis_monitoring_unavailable")
        return _empty_metrics()

    metrics: dict = {}

    #Memória
    try:
        mem_info = client.info("memory")
        metrics["memory_used_bytes"] = mem_info.get("used_memory")
        metrics["memory_used_human"] = mem_info.get("used_memory_human")
        metrics["memory_peak_human"] = mem_info.get("used_memory_peak_human")
        metrics["memory_maxmemory_human"] = mem_info.get("maxmemory_human")
        metrics["memory_fragmentation_ratio"] = mem_info.get("mem_fragmentation_ratio")
    except Exception:
        logger.warning("redis_monitoring_memory_failed", exc_info=True)
        metrics.update({
            "memory_used_bytes": None,
            "memory_used_human": None,
            "memory_peak_human": None,
            "memory_maxmemory_human": None,
            "memory_fragmentation_ratio": None,
        })

    #Total de chaves no DB operacional (db 2)
    try:
        metrics["keys_total"] = client.dbsize()
    except Exception:
        logger.warning("redis_monitoring_dbsize_failed", exc_info=True)
        metrics["keys_total"] = None

    #DLQ backlog (stream)
    try:
        dlq_key = settings.CELERY_DLQ_STREAM_NAME
        metrics["dlq_backlog"] = client.xlen(dlq_key)
    except Exception:
        logger.warning("redis_monitoring_dlq_failed", exc_info=True)
        metrics["dlq_backlog"] = None

    #Métricas de orquestração Temporal via snapshots Redis (best-effort)
    try:
        import json as _json
        snapshot_keys = client.keys("workflow:snapshot:*")
        pending_count = 0
        processing_count = 0
        for key in snapshot_keys:
            raw = client.get(key)
            if raw:
                state = _json.loads(raw).get("state", "")
                if state in ("WaitingTimer", "Active", "Backoff"):
                    pending_count += 1
                elif state in ("Dispatching", "WaitingResult"):
                    processing_count += 1
        metrics["queue_pending"] = pending_count
        metrics["queue_processing"] = processing_count
    except Exception:
        logger.warning("redis_monitoring_temporal_snapshots_failed", exc_info=True)
        metrics["queue_pending"] = None
        metrics["queue_processing"] = None

    logger.debug("redis_metrics_collected", **{k: v for k, v in metrics.items() if v is not None})
    return metrics

def _empty_metrics() -> dict:
    return {
        "memory_used_bytes": None,
        "memory_used_human": None,
        "memory_peak_human": None,
        "memory_maxmemory_human": None,
        "memory_fragmentation_ratio": None,
        "keys_total": None,
        "dlq_backlog": None,
        "queue_pending": None,
        "queue_processing": None,
    }
