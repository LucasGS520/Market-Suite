""" Inicialização de clientes Redis e utilidades compartilhadas

Este módulo provê funções reutilizadas nos serviços para recuperar
clientes isolados por thread, criar chaves com TTL e aplicar limites
de taxa baseados em Redis. Ele também concentra a lógica do *leaky
bucket* utilizada pelas rotas HTTP para evitar explosões de requisições.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Tuple
import redis

from shared.core.config_base import ConfigBase


#Armazena instâncias isoladas de Redis por thread
_thread_local = threading.local()
logger = logging.getLogger(__name__)
SCRAPING_SUSPENDED_KEY = "scraping:suspended"
_settings = ConfigBase()

_LEAKY_BUCKET_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local leak_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

local state = redis.call('GET', key)
local tokens = 0.0
local last = now

if state then
    local separator = string.find(state, '|')
    if separator then
        tokens = tonumber(string.sub(state, 1, separator - 1)) or 0.0
        last = tonumber(string.sub(state, separator + 1)) or now
    else
        tokens = tonumber(state) or 0.0
    end
    local elapsed = now - last
    if elapsed > 0 then
        local leaked = elapsed * leak_rate
        tokens = tokens - leaked
        if tokens < 0 then
            tokens = 0.0
        end
    end
end

local allowed = 0
if tokens < capacity then
    tokens = tokens + 1
    allowed = 1
end

redis.call('SET', key, string.format('%.4f|%.4f', tokens, now), 'EX', ttl)

return {allowed, tokens}
"""

_TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

local state = redis.call('GET', key)
local tokens = capacity
local last = now

if state then
    local separator = string.find(state, '|')
    if separator then
        tokens = tonumber(string.sub(state, 1, separator - 1)) or capacity
        last = tonumber(string.sub(state, separator + 1)) or now
    else
        tokens = tonumber(state) or capacity
    end
    local elapsed = now - last
    if elapsed > 0 then
        local refill = elapsed * refill_rate
        tokens = tokens + refill
        if tokens > capacity then
            tokens = capacity
        end
    end
end

local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end

redis.call('SET', key, string.format('%.4f|%.4f', tokens, now), 'EX', ttl)

return {allowed, tokens}
"""

_registered_scripts: dict[int, Any] = {}
_registered_token_bucket_scripts: dict[int, Any] = {}

def get_redis_client() -> redis.Redis | None:
    """ Retorna cliente Redis isolado por thread (usa REDIS_DB genérico).

    Mantido para retrocompatibilidade. Para código de aplicação, prefira
    ``get_redis_operational()`` que conecta explicitamente no db operacional.
    """
    client = getattr(_thread_local, "client", None)
    if client is None:
        try:
            _thread_local.client = redis.Redis.from_url(
                _settings.redis_url, decode_responses=True, socket_timeout=2.0
            )
            client = _thread_local.client
        except Exception as err:
            logger.error("falha_inicializacao_redis", erro=str(err))
            return None
    return client

def get_redis_operational() -> redis.Redis | None:
    """ Retorna cliente Redis do db operacional, isolado por thread.

    Conecta no ``REDIS_OPERATIONAL_DB`` (db 2 por padrão) — camada dedicada
    a locks, rate limiting, cache, DLQ e filas operacionais. Separada do
    broker Celery (db 0) e do result backend (db 1) para evitar interferência.
    """
    client = getattr(_thread_local, "operational_client", None)
    if client is None:
        try:
            _thread_local.operational_client = redis.Redis.from_url(
                _settings.redis_operational_url, decode_responses=True, socket_timeout=2.0
            )
            client = _thread_local.operational_client
        except Exception as err:
            logger.error("falha_inicializacao_redis_operacional", erro=str(err))
            return None
    return client

def set_key_with_ttl(key: str, value: Any, ttl_seconds: int, *, only_if_absent: bool = False) -> bool | None:
    """ Define uma chave no Redis operacional com TTL controlado """
    client = get_redis_operational()
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

def consume_leaky_bucket(
    key: str,
    *,
    capacity: int,
    leak_rate_per_second: float,
    ttl_seconds: int | None = None,
    now: float | None = None,
) -> Tuple[bool, float | None]:
    """ Consome um *token* do balde vazante controlando limites de requisições.

    A função aplica um algoritmo de *leaky bucket* no Redis. Em cada chamada,
    calculamos a quantidade de *tokens* que deveriam ter vazado desde o último
    registro e, se o balde ainda não está cheio, consumimos um novo *token*.
    Quando o Redis não estiver disponível, consideramos a requisição permitida
    para manter o serviço funcional.

    Parâmetros
    ----------
    key:
        Chave única que identifica o balde (ex.: ``rate:user:123``).
    capacity:
        Quantidade máxima de requisições acumuladas permitidas no intervalo.
    leak_rate_per_second:
        Taxa de vazão em tokens por segundo (``capacity / janela``).
    ttl_seconds:
        Tempo de vida do registro no Redis. Se omitido, utiliza duas janelas
        completas como margem de segurança.
    now:
        Timestamp atual em segundos. Mantido parametrizável para facilitar
        testes determinísticos.

    Retorno
    -------
    tuple[bool, float | None]
        ``(permitido, tokens_atualizados)``. O segundo valor pode ser ``None``
        quando o Redis estiver indisponível.
    """
    client = get_redis_operational()
    if client is None:
        logger.warning("leaky_bucket_disabled", reason="redis_unavailable", key=key)
        return True, None

    if capacity <= 0 or leak_rate_per_second <= 0:
        logger.warning("leaky_bucket_invalid_parameters", key=key)
        return True, None

    current_time = now or time.time()
    ttl = ttl_seconds
    if ttl is None:
        window_seconds = max(1.0, capacity / leak_rate_per_second)
        ttl = max(1, int(math.ceil(window_seconds * 2)))

    try:
        client_id = id(client)
        script = _registered_scripts.get(client_id)
        if script is None:
            script = client.register_script(_LEAKY_BUCKET_SCRIPT)
            _registered_scripts[client_id] = script

        allowed, tokens = script(
            keys=[key],
            args=[capacity, leak_rate_per_second, current_time, ttl],
        )
        return bool(int(allowed)), float(tokens)
    except Exception as exc:  # pragma: no cover - proteção contra falhas externas
        logger.warning("leaky_bucket_execution_failed", key=key, error=str(exc))
        return True, None
    
def consume_token_bucket(
    key: str,
    *,
    capacity: int,
    refill_rate_per_second: float,
    ttl_seconds: int | None = None,
    now: float | None = None,
    client: redis.Redis | None = None,
) -> Tuple[bool, float | None]:
    """ Aplica *token bucket* no Redis para limitar vazão por chave

    Quando o Redis estiver indisponível, a função permite a requisição
    para evitar travamento do fluxo de scraping

    Parâmetros
    ----------
    key:
        Chave única que identifica o bucket (ex.: ``rate:host:example``).
    capacity:
        Capacidade máxima de tokens acumulados
    refill_rate_per_second:
        Taxa de reposição de tokens por segundo
    ttl_seconds:
        Tempo de vida da chave no Redis. Se omitido, usa duas janelas completas
    now:
        Timestamp atual em segundos, útil para testes determinísticos
    client:
        Cliente Redis opcional para reaproveitar conexões existentes

    Retorno
    -------
    tuple[bool, float | None]
        ``(permitido, tokens_restantes)``. O segundo valor é ``None`` em falhas.
    """
    redis_client = client or get_redis_operational()
    if redis_client is None:
        logger.warning("token_bucket_disabled", reason="redis_unavailable", key=key)
        return True, None
    
    if capacity <= 0 or refill_rate_per_second <= 0:
        logger.warning("token_bucket_invalid_parameters", key=key)
        return True, None
    
    current_time = now or time.time()
    ttl = ttl_seconds
    if ttl is None:
        window_seconds = max(1.0, capacity / refill_rate_per_second)
        ttl = max(1, int(math.ceil(window_seconds * 2)))

    try:
        client_id = id(redis_client)
        script = _registered_token_bucket_scripts.get(client_id)
        if script is None:
            script = redis_client.register_script(_TOKEN_BUCKET_SCRIPT)
            _registered_token_bucket_scripts[client_id] = script

        allowed, tokens = script(
            keys=[key],
            args=[capacity, refill_rate_per_second, current_time, ttl],
        )
        return bool(int(allowed)), float(tokens)
    except Exception as exc:
        logger.warning("token_bucket_execution_failed", key=key, error=str(exc))
        return True, None

def key_exists(key: str) -> bool:
    """ Verifica de forma resiliente se uma chave existe no Redis operacional """
    client = get_redis_operational()
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
    """ Remove uma chave específica do Redis operacional, ignorando falhas de conexão """
    client = get_redis_operational()
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
    """ Verifica se a flag de suspensão de scraping está ativa (db operacional) """
    client = get_redis_operational()
    if client is None:
        return False
    exists = getattr(client, "exists", None)
    active = exists(SCRAPING_SUSPENDED_KEY) == 1 if exists else False
    return active

def suspend_scraping(duration_seconds: int) -> None:
    """ Ativa a flag global de suspensão de scraping por ``duration_seconds`` segundos """
    client = get_redis_operational()
    if client is None:
        return
    setter = getattr(client, "set", None)
    if setter:
        setter(SCRAPING_SUSPENDED_KEY, "1", ex=duration_seconds)

def resume_scraping() -> None:
    """ Remove imediatamente a flag de suspensão, permitindo o scraping """
    client = get_redis_operational()
    if client is None:
        return
    deleter = getattr(client, "delete", None)
    if deleter:
        deleter(SCRAPING_SUSPENDED_KEY)
