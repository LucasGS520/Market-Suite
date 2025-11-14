""" Inicialização e acesso compartilhado ao cliente Redis

Reutilizado por `market_alert` e `market_scraper` para gerenciar
a flag de suspensão de scraping
"""

import logging
import threading
from typing import Any
import redis

from shared.core.config_base import ConfigBase
from shared import metrics


#Armazena instâncias isoladas de Redis por thread
_thread_local = threading.local()
logger = logging.getLogger(__name__)
SCRAPING_SUSPENDED_KEY = "scraping:suspended"
_settings = ConfigBase()

def get_redis_client() -> redis.Redis | None:
    """ Retorna um cliente Redis isolado por thread

    Cria o cliente na primeira chamada da thread e o reutiliza nas
    chamadas subsequentes, evitando o compartilhamento entre threads
    ou processos diferentes. Caso a conexão com o Redis falhe, retorna ``None``.

    Retorno
    -------
    redis.Redis | None
        Instância de cliente Redis pronta para o uso ou ``None`` quando
        não for possível inicializar a conexão.
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

def set_key_with_ttl(key: str, value: Any, ttl_seconds: int, *, only_if_absent: bool = False) -> bool | None:
    """ Define uma chave no Redis com TTL controlado """

    client = get_redis_client()
    if client is None:
        return None

    try:
        result = client.set(key, value, ex=ttl_seconds, nx=only_if_absent)
    except TypeError:
        exists = getattr(client, "exists", None)
        if only_if_absent and callable(exists) and exists(key):
            return False

        setter = getattr(client, "set", None)
        if not callable(setter):
            return None

        try:
            setter(key, value)
            expire = getattr(client, "expire", None)
            if callable(expire) and ttl_seconds > 0:
                expire(key, ttl_seconds)
        except Exception as err:  # pragma: no cover - falha inesperada
            logger.error(
                "falha_definir_chave_redis",
                extra={"chave": key, "erro": str(err)},
            )
            return None
        return True
    except Exception as err:  # pragma: no cover - erros não previstos
        logger.error(
            "falha_definir_chave_redis",
            extra={"chave": key, "erro": str(err)},
        )
        return None

    return bool(result)


def key_exists(key: str) -> bool:
    """ Verifica de forma resiliente se uma chave existe no Redis """

    client = get_redis_client()
    if client is None:
        return False

    exists = getattr(client, "exists", None)
    if exists is None:
        return False

    try:
        return bool(exists(key))
    except Exception as err:  # pragma: no cover - comportamento inesperado
        logger.error(
            "falha_consultar_chave_redis",
            extra={"chave": key, "erro": str(err)},
        )
        return False


def delete_key(key: str) -> None:
    """ Remove uma chave específica, ignorando falhas de conexão """

    client = get_redis_client()
    if client is None:
        return

    deleter = getattr(client, "delete", None)
    if deleter is None:
        return

    try:
        deleter(key)
    except Exception as err:  # pragma: no cover - comportamento inesperado
        logger.error(
            "falha_remover_chave_redis",
            extra={"chave": key, "erro": str(err)},
        )

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
