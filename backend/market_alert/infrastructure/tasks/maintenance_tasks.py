""" Tarefas de manutenção periódica do cache de scraping no Redis """

from __future__ import annotations

import time

import structlog
from celery import shared_task

from shared.utils.redis_client import get_redis_operational

from market_alert.core.config_alert import settings


logger = structlog.get_logger("maintenance_tasks")

@shared_task(name="market_alert.infrastructure.tasks.maintenance_tasks.cleanup_cache")
def cleanup_cache() -> None:
    """ Remove chaves de cache com TTL inválido sem bloquear o Redis.

    A rotina percorre o namespace ``cache:*`` com ``SCAN`` incremental,
    agrupa ``UNLINK`` em lotes e aplica limites de duração/volume para
    reduzir risco operacional em bases muito grandes.
    """
    removed = 0
    no_expiration = 0
    expired = 0
    scanned_keys = 0
    scan_iterations = 0
    redis_client = get_redis_operational()
    if redis_client is None:
        logger.warning("cleanup_cache_skipped", reason="redis_unavailable")
        return
    
    started_at = time.monotonic()
    max_duration_seconds = max(1.0, float(settings.CLEANUP_CACHE_MAX_DURATION_SECONDS))
    max_keys_per_run = max(1, int(settings.CLEANUP_CACHE_MAX_KEYS_PER_RUN))
    scan_count = max(10, int(settings.CLEANUP_CACHE_SCAN_COUNT))
    unlink_batch_size = max(10, int(settings.CLEANUP_CACHE_UNLINK_BATCH_SIZE))
    sleep_between_batches_ms = max(0, int(settings.CLEANUP_CACHE_SLEEP_BETWEEN_BATCHES_MS))

    def _flush_unlink_batch(pending_keys: list[str]) -> int:
        """ Executa UNLINK em lote e retorna quantas chaves foram enviadas. """
        if not pending_keys:
            return 0
        unlink_pipeline = redis_client.pipeline()
        #UNLINK é não bloqueante para liberar memória sem travar o Redis.
        unlink_pipeline.unlink(*pending_keys)
        unlink_pipeline.execute()
        if sleep_between_batches_ms > 0:
            #Pausa opcional para reduzir pressão quando há milhões de chaves.
            time.sleep(sleep_between_batches_ms / 1000)
        return len(pending_keys)
    
    try:
        cursor = 0
        pending_unlink_keys: list[str] = []
        stopped_by_limit = False
        stop_reason: str | None = None

        #SCAN incremental evita varredura bloqueante em produção.
        while True:
            elapsed = time.monotonic() - started_at
            if elapsed >= max_duration_seconds:
                stopped_by_limit = True
                stop_reason = "max_duration_reached"
                break
            if scanned_keys >= max_keys_per_run:
                stopped_by_limit = True
                stop_reason = "max_keys_reached"
                break

            cursor, keys = redis_client.scan(cursor=cursor, match="cache:*", count=scan_count)
            scan_iterations += 1
            scanned_keys += len(keys)
            if keys:
                ttl_pipeline = redis_client.pipeline()
                for key in keys:
                    ttl_pipeline.ttl(key)
                ttls = ttl_pipeline.execute()
                for key, ttl in zip(keys, ttls):
                    #Separar motivos ajuda a calibrar política de expiração.
                    if ttl == -1:
                        pending_unlink_keys.append(key)
                        removed += 1
                        no_expiration += 1
                        continue
                    if ttl <= 0:
                        pending_unlink_keys.append(key)
                        removed += 1
                        expired += 1

                while len(pending_unlink_keys) >= unlink_batch_size:
                    batch = pending_unlink_keys[:unlink_batch_size]
                    pending_unlink_keys = pending_unlink_keys[unlink_batch_size:]
                    _flush_unlink_batch(batch)

            if cursor == 0:
                break

        if pending_unlink_keys:
            _flush_unlink_batch(pending_unlink_keys)
            
        logger.info(
            "cleanup_cache_success",
            removed=removed,
            no_expiration=no_expiration,
            expired=expired,
            scanned_keys=scanned_keys,
            scan_iterations=scan_iterations,
            stopped_by_limit=stopped_by_limit,
            stop_reason=stop_reason,
            duration_seconds=round(time.monotonic() - started_at, 3),
            scan_count=scan_count,
            unlink_batch_size=unlink_batch_size,
            max_keys_per_run=max_keys_per_run,
            max_duration_seconds=max_duration_seconds,
            sleep_between_batches_ms=sleep_between_batches_ms,
        )
    except Exception:
        logger.exception("cleanup_cache_failure")
        