""" Tarefas de manutenção e limpeza perióidica para o serviço """

import structlog
from celery import shared_task

from shared.utils.redis_client import get_redis_client


logger = structlog.get_logger("maintenance_tasks")


@shared_task(name="market_alert.tasks.maintenance_tasks.cleanup_cache")
def cleanup_cache() -> None:
    """ Remove entradas expiradas ou sem TTL do cache de Scraping """
    removed = 0
    redis_client = get_redis_client()
    if redis_client is None:
        logger.warning("cleanup_cache_skipped", reason="redis_unavailable")
        return
    
    try:
        cursor = 0
        #Percorre chaves iniciadas com "cache": utilizando SCAN para evitar bloqueios
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match="cache:*", count=100)
            for key in keys:
                ttl = redis_client.ttl(key)
                # -2 significa que a chave não existe mais; -1 indica ausência de expiração
                if ttl == -2:
                    continue
                if ttl <= 0:
                    redis_client.delete(key)
                    removed += 1
            if cursor == 0:
                break
            
        logger.info("cleanup_cache_success", removed=removed)
    except Exception:
        logger.exception("cleanup_cache_failure")
        