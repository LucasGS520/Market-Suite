""" Rate limiter usando janela deslizante em Redis """

import time
import os
from typing import Optional

from utils.redis_client import get_redis_client


def _load_lua_script(redis):
    """ Carrega e cacheia o script Lua utilizado para rate limiting """
    if not hasattr(_load_lua_script, "sha"):
        lua_path = os.path.join(
            os.path.dirname(__file__),
            os.pardir,
            os.pardir,
            "infra",
            "redis-scripts",
            "sliding_window.lua",
        )

        with open(lua_path, "r", encoding="utf-8") as f:
            lua_source = f.read()

        _load_lua_script.sha = redis.script_load(lua_source)
    return _load_lua_script.sha

class RateLimiter:
    """ Limitador de taxa global de Sliding-window usando script Lua no Redis """
    def __init__(self, redis_key: str, max_requests: int, window_seconds: int):
        self.redis = get_redis_client()
        self.key = redis_key
        self.limit = max_requests
        self.window = window_seconds
        self.window_ms = window_seconds * 1000

        #Carrega o script lua apenas uma vez e guarda o SHA para reuso
        self.lua_sha = _load_lua_script(self.redis)

    def _format_key(self, identifier: Optional[str]) -> str:
        """ Se necessário sub-limits (por usuário, por endpoint) é utilizado ``identifier`` """
        return f"{self.key}:{identifier}" if identifier else self.key

    def allow_request(self, identifier: Optional[str] = None) -> bool:
        """ Executa o script Lua e retorna ``True`` se estiver dentro do limite """
        redis_key = self._format_key(identifier)
        now_ms = int(time.time() * 1000)

        allowed = self.redis.evalsha(self.lua_sha, 1, redis_key, now_ms, self.window_ms, self.limit)
        return allowed == 1

    def get_count(self, identifier: Optional[str] = None) -> int:
        """ Retorna quantas requisições foram feitas na janela atual """
        redis_key = self._format_key(identifier)
        now_ms = int(time.time() * 1000)
        window_start = now_ms - self.window_ms

        #Remove timestamp fora da janela e conta o restante
        self.redis.zremrangebyscore(redis_key, 0, window_start)
        return self.redis.zcard(redis_key)

    def reset(self, identifier: Optional[str] = None) -> None:
        """ Limpa completamente o estado do rate limiter """
        self.redis.delete(self._format_key(identifier))
