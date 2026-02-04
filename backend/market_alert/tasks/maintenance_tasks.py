""" Tarefas de manutenção periódica do cache de scraping no Redis """

import structlog
from celery import shared_task

from shared.utils.redis_client import get_redis_client


logger = structlog.get_logger("maintenance_tasks")


@shared_task(name="market_alert.tasks.maintenance_tasks.cleanup_cache")
def cleanup_cache() -> None:
    """ Remove entradas do cache de scraping sem expiração (TTL == -1) ou expiradas (TTL <= 0).

    A política remove chaves sem TTL para evitar crescimento indefinido do cache e
    elimina chaves expiradas para manter apenas dados válidos para o scraping.
    """
    removed = 0
    no_expiration = 0
    expired = 0
    redis_client = get_redis_client()
    if redis_client is None:
        logger.warning("cleanup_cache_skipped", reason="redis_unavailable")
        return
    
    try:
        cursor = 0
        unlink_batch_size = 200
        pending_unlink_keys = []
        #Percorre chaves iniciadas com "cache": utilizando SCAN para evitar bloqueios
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match="cache:*", count=100)
            if keys:
                ttl_pipeline = redis_client.pipeline()
                for key in keys:
                    ttl_pipeline.ttl(key)
                ttls = ttl_pipeline.execute()
                for key, ttl in zip(keys, ttls):
                    #Registra contadores separados para diagnosticar chaves sem expiração versus expirados
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
                    unlink_pipeline = redis_client.pipeline()
                    #O pipeline reduz latência e carga no Redis ao agrupar comandos UNLINK
                    unlink_pipeline.unlink(*batch)
                    unlink_pipeline.execute()
            if cursor == 0:
                break

        if pending_unlink_keys:
            unlink_pipeline = redis_client.pipeline()
            #O pipeline reduz latência e carga no Redis ao agrupar comandos UNLINK
            unlink_pipeline.unlink(*pending_unlink_keys)
            unlink_pipeline.execute()
            
        logger.info(
            "cleanup_cache_success",
            removed=removed,
            no_expiration=no_expiration,
            expired=expired,
        )
    except Exception:
        logger.exception("cleanup_cache_failure")
        