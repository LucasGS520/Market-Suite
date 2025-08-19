""" Inicialização e acesso compartilhado ao cliente Redis

Reutilizado por `market_alert` e `market_scraper` para gerenciar
a flag de suspensão de scraping
"""

import logging
import threading
import redis

from shared.core.config_base import ConfigBase
from shared import metrics


#Armazena instâncias isoladas de Redis por thread
_thread_local = threading.local()
logger = logging.getLogger(__name__)
SCRAPING_SUSPENDED_KEY = "scraping:suspended"
_settings = ConfigBase()

def get_redis_client() -> redis.Redis:
    """ Retorna um cliente Redis isolado por thread

    Cria o cliente na primeira chamada da thread e o reutiliza nas
    chamadas subsequentes, evitando o compartilhamento entre threads
    ou processos diferentes.
    """
    client = getattr(_thread_local, "client", None)
    if client is None:
        try:
            _thread_local.client = redis.Redis.from_url(
                _settings.redis_url, decode_responses=True
            )
            client = _thread_local.client
        except Exception as err:
            metrics.REDIS_CONNECTION_ERRORS_TOTAL.inc()
            logger.error("falha_inicializacao_redis", erro=str(err))
            return None
    return client

def is_scraping_suspended() -> bool:
    """ Verifica se a flag de suspensão de scraping está ativa """
    client = get_redis_client()
    if client is None:
        metrics.SCRAPING_SUSPENDED_FLAG.set(0)
        return False
    exists = getattr(client, "exists", None)
    active = exists(SCRAPING_SUSPENDED_KEY) == 1 if exists else False
    metrics.SCRAPING_SUSPENDED_FLAG.set(1 if active else 0)
    return active

def suspend_scraping(duration_seconds: int) -> None:
    """ Ativa a flag global de suspensão de scraping por ``duration_seconds`` segundos """
    client = get_redis_client()
    if client is None:
        return
    setter = getattr(client, "set", None)
    if setter:
        setter(SCRAPING_SUSPENDED_KEY, "1", ex=duration_seconds)
        metrics.SCRAPING_SUSPENDED_FLAG.set(1)

def resume_scraping() -> None:
    """ Remove imediatamente a flag de suspensão, permitindo o scraping """
    client = get_redis_client()
    if client is None:
        return
    deleter = getattr(client, "delete", None)
    if deleter:
        deleter(SCRAPING_SUSPENDED_KEY)
        metrics.SCRAPING_SUSPENDED_FLAG.set(0)
