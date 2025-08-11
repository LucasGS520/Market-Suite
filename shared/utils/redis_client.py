""" Inicialização e acesso compartilhado ao cliente Redis

Reutilizado por `market_alert` e `market_scraper` para gerenciar
a flag de suspensão de scraping
"""

import redis
from typing import Optional

from shared.core.config_base import ConfigBase
from shared import metrics


#Cliente Redis utilizado por ``market_alert`` e ``market_scraper``
_redis_client: Optional[redis.Redis] = None
SCRAPING_SUSPENDED_KEY = "scraping:suspended"
_settings = ConfigBase()

def get_redis_client() -> redis.Redis:
    """ Retorna uma instância singleton de Redis, usando a URL configurada """
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(_settings.redis_url, decode_responses=True)
    return _redis_client

def is_scraping_suspended() -> bool:
    """ Verifica se a flag de scraping está ativa """
    client = get_redis_client()
    exists = getattr(client, "exists", None)
    active = exists(SCRAPING_SUSPENDED_KEY) == 1 if exists else False
    metrics.SCRAPING_SUSPENDED_FLAG.set(1 if active else 0)
    return active

def suspend_scraping(duration_seconds: int) -> None:
    """ Ativa a flag de suspensão de scraping por ``duration_seconds`` """
    client = get_redis_client()
    setter = getattr(client, "set", None)
    if setter:
        setter(SCRAPING_SUSPENDED_KEY, "1", ex=duration_seconds)
        metrics.SCRAPING_SUSPENDED_FLAG.set(1)

def resume_scraping() -> None:
    """ Remove imediatamente a flag de suspensão, permitindo o scraping """
    client = get_redis_client()
    deleter = getattr(client, "delete", None)
    if deleter:
        deleter(SCRAPING_SUSPENDED_KEY)
        metrics.SCRAPING_SUSPENDED_FLAG.set(0)
