""" Utilitários de limitação de taxa usando Redis e script Lua

Empregado pelo ``market_scraper`` para controlar requisições
de forma global e evitar sobrecarga nos sites alvo.
"""

from __future__ import annotations

import os
import time
from typing import Optional

import structlog

from shared.metrics.metrics_scraper import (
    SCRAPER_RATE_LIMIT_LATENCY_SECONDS,
    SCRAPER_RATE_LIMIT_MODE,
    SCRAPER_RATE_LIMIT_REQUESTS_TOTAL,
)
from shared.utils.logging_utils import sanitize_log_data
from shared.utils.redis_client import get_redis_client


logger = structlog.get_logger(__name__)

def _load_lua_script(redis):
    """ Carrega e cacheia o script Lua utilizado para rate limiting """
    if not hasattr(_load_lua_script, "sha"):
        lua_path = os.path.join(
            os.path.dirname(__file__),
            os.pardir,
            os.pardir,
            "shared",
            "infra",
            "redis-scripts",
            "sliding_window.lua",
        ) #Caminho final: shared/infra/redis-scripts/sliding_window.lua

        with open(lua_path, "r", encoding="utf-8") as f:
            lua_source = f.read()

        _load_lua_script.sha = redis.script_load(lua_source)
    return _load_lua_script.sha

class RateLimiter:
    """ Limitador de taxa global de Sliding-window usando script Lua no Redis """
    def __init__(
        self, 
        redis_key: str, 
        max_requests: int, 
        window_seconds: int,
        *,
        metrics_host: str | None = None,
    ) -> None:
        """ Inicializa o limitador e prepara recursos necessários

        Quando não há conexão com Redis disponível o limitador entra em modo
        passivo, permitindo todas as requisições sem aplicar restrições.
        """
        self.redis = get_redis_client()
        self.key = redis_key
        self.limit = max_requests
        self.window = window_seconds
        self.window_ms = window_seconds * 1000
        self.metrics_host = metrics_host or "global"

        if self.redis is None:
            #Sem Redis, não carrega o script e sempre permite requisições
            self.lua_sha = None
            SCRAPER_RATE_LIMIT_MODE.labels(host=self.metrics_host).set(0)
        else:
            #Carrega o script Lua apenas uma vez e guarda o SHA para reuso
            try:
                self.lua_sha = _load_lua_script(self.redis)
                SCRAPER_RATE_LIMIT_MODE.labels(host=self.metrics_host).set(1)
            except Exception as err:
                logger.warning(
                    "rate_limiter_lua_load_error",
                    key=sanitize_log_data(self.key),
                    error=sanitize_log_data(str(err)),
                )
                self.lua_sha = None
                self.redis = None
                SCRAPER_RATE_LIMIT_MODE.labels(host=self.metrics_host).set(0)

    def _format_key(self, identifier: Optional[str]) -> str:
        """ Se necessário sub-limits (por usuário, por endpoint) é utilizado ``identifier`` """
        return f"{self.key}:{identifier}" if identifier else self.key

    def allow_request(self, identifier: Optional[str] = None) -> bool:
        """ Executa o script Lua e indica se a requisição é permitida

        Quando o Redis está indisponível, todas as requisições são aceitas
        """
        start = time.perf_counter()

        if self.redis is None:
            SCRAPER_RATE_LIMIT_REQUESTS_TOTAL.labels(
                host=self.metrics_host,
                result="passive",
            ).inc()
            SCRAPER_RATE_LIMIT_LATENCY_SECONDS.labels(host=self.metrics_host).observe(
                time.perf_counter() - start
            )
            return True

        redis_key = self._format_key(identifier)
        now_ms = int(time.time() * 1000)

        try:
            allowed = self.redis.evalsha(
                self.lua_sha, 1, redis_key, now_ms, self.window_ms, self.limit
            )
        except Exception as err:
            SCRAPER_RATE_LIMIT_MODE.labels(host=self.metrics_host).set(0)
            SCRAPER_RATE_LIMIT_REQUESTS_TOTAL.labels(
                host=self.metrics_host,
                result="error",
            ).inc()
            logger.warning(
                "rate_limiter_eval_error",
                key=sanitize_log_data(redis_key),
                error=sanitize_log_data(str(err)),
            )
            SCRAPER_RATE_LIMIT_LATENCY_SECONDS.labels(host=self.metrics_host).observe(
                time.perf_counter() - start
            )
            return True
        
        result_label = "allowed" if allowed == 1 else "blocked"
        SCRAPER_RATE_LIMIT_MODE.labels(host=self.metrics_host).set(1)
        SCRAPER_RATE_LIMIT_REQUESTS_TOTAL.labels(
            host=self.metrics_host,
            result=result_label,
        ).inc()
        SCRAPER_RATE_LIMIT_LATENCY_SECONDS.labels(host=self.metrics_host).observe(
            time.perf_counter() - start
        )
        return allowed == 1

    def get_count(self, identifier: Optional[str] = None) -> int:
        """ Retorna quantas requisições foram feitas na janela atual

        Quando o Redis está indisponível, a contagem não é realizada e o
        valor ``0`` é retornado
        """
        if self.redis is None:
            return 0

        redis_key = self._format_key(identifier)
        now_ms = int(time.time() * 1000)
        window_start = now_ms - self.window_ms

        try:
            #Remove timestamp fora da janela e conta o restante
            self.redis.zremrangebyscore(redis_key, 0, window_start)
            SCRAPER_RATE_LIMIT_MODE.labels(host=self.metrics_host).set(1)
            return self.redis.zcard(redis_key)
        except Exception as err:
            logger.warning(
                "rate_limiter_count_error",
                key=sanitize_log_data(redis_key),
                error=sanitize_log_data(str(err)),
            )
            SCRAPER_RATE_LIMIT_MODE.labels(host=self.metrics_host).set(0)
            return 0

    def reset(self, identifier: Optional[str] = None) -> None:
        """ Limpa completamente o estado do rate limiter

        Caso o Redis esteja indisponível, a operação é ignorada
        """
        if self.redis is None:
            return
        redis_key = self._format_key(identifier)
        try:
            self.redis.delete(redis_key)
            SCRAPER_RATE_LIMIT_MODE.labels(host=self.metrics_host).set(1)
        except Exception as err:
            logger.warning(
                "rate_limiter_reset_error",
                key=sanitize_log_data(redis_key),
                error=sanitize_log_data(str(err)),
            )
            SCRAPER_RATE_LIMIT_MODE.labels(host=self.metrics_host).set(0)
