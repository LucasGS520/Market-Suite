""" Métricas operacionais do Redis para monitoramento e alertas.

Expõe snapshot das métricas críticas de saúde do Redis, cobrindo:
- Uso de memória
- Tamanho de chaves por DB
- Backlog da DLQ (stream Celery)
- Profundidade das filas Celery no broker (scraping, compare, notifications)
- Workflows em estado ativo/processando (via snapshots Redis)

Uso::

    from market_alert.infraestructure.redis_monitoring import get_redis_metrics

    metrics = get_redis_metrics()
    # metrics["memory_used_human"] → "42.5M"
    # metrics["dlq_backlog"] → 0
    # metrics["queue_pending"] → 15
    # metrics["celery_queue_scraping"] → 3  (tasks aguardando na fila)

Degradação segura: todas as métricas retornam None em caso de falha no Redis,
permitindo que o endpoint de health continue respondendo sem lançar exceção.
"""

from __future__ import annotations

import json as _json

import structlog
import redis as _redis_lib

from shared.utils.redis_client import get_redis_operational
from market_alert.core.config_alert import settings


logger = structlog.get_logger("redis_monitoring")

# Limite de snapshots inspecionados por chamada (protege contra scan excessivo)
_SNAPSHOT_SCAN_LIMIT = 500


def _get_broker_client() -> _redis_lib.Redis | None:
    """ Retorna cliente Redis do DB do broker Celery (db 0 por padrão).

    Separado do cliente operacional (db 2) para não contaminar locks/cache.
    Falhas retornam None — as métricas ficam como None no resultado.
    """
    try:
        return _redis_lib.Redis.from_url(
            settings.celery_broker_url,
            decode_responses=True,
            socket_timeout=1.0,
        )
    except Exception:
        return None


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

    #Profundidade das filas Celery no broker (DB 0) — usa LLEN que é O(1)
    #Celery armazena cada fila como uma lista Redis com o nome da fila como chave.
    try:
        broker = _get_broker_client()
        if broker is not None:
            metrics["celery_queue_scraping"] = broker.llen("scraping")
            metrics["celery_queue_compare"] = broker.llen("compare")
            metrics["celery_queue_notifications"] = broker.llen("notifications")
        else:
            metrics["celery_queue_scraping"] = None
            metrics["celery_queue_compare"] = None
            metrics["celery_queue_notifications"] = None
    except Exception:
        logger.warning("redis_monitoring_celery_queues_failed", exc_info=True)
        metrics["celery_queue_scraping"] = None
        metrics["celery_queue_compare"] = None
        metrics["celery_queue_notifications"] = None

    #Métricas de orquestração Temporal via snapshots Redis (SCAN — não bloqueante)
    #client.keys() é O(N) e bloqueia o Redis; SCAN itera incrementalmente.
    try:
        pending_count = 0
        processing_count = 0
        scanned = 0
        for key in client.scan_iter("workflow:snapshot:*", count=100):
            if scanned >= _SNAPSHOT_SCAN_LIMIT:
                break
            scanned += 1
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
        "celery_queue_scraping": None,
        "celery_queue_compare": None,
        "celery_queue_notifications": None,
        "queue_pending": None,
        "queue_processing": None,
    }
