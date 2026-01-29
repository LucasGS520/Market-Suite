""" Fixtures e utilidades comuns para os testes unitários dos componentes compartilhados """

import pytest
import time
from backend.shared.utils import redis_locks as redis_locks_module

#FakeRedis universal para testes unitários
class FakeRedis:
    """Simula cliente Redis com comandos mínimos usados pelos utilitários."""
    def __init__(self):
        self.data = {}
        self.scripts = {}

    def script_load(self, source):
        sha = f"fake-sha-{len(self.scripts)}"
        self.scripts[sha] = source
        return sha

    def set(self, key, value, ex=None, px=None, nx=False):
        """Armazena valor respeitando flags de não sobreposição e TTL."""

        if nx and key in self.data:
            return False
        
        self.data[key] = value
        ttl_value = ex if ex is not None else (px / 1000 if px is not None else None)
        if ttl_value is not None:
            self.data[f"ttl:{key}"] = ttl_value

        return True

    def get(self, key):
        return self.data.get(key)

    def exists(self, key):
        return key in self.data

    def evalsha(self, sha, num_keys, redis_key, now_ms, window_ms, limit):
        if redis_key not in self.data:
            self.data[redis_key] = []

        window_start = now_ms - window_ms
        self.data[redis_key] = [ts for ts in self.data[redis_key] if ts > window_start]
        self.data[redis_key].append(now_ms)
        return 1 if len(self.data[redis_key]) <= limit else 0

    def incr(self, key):
        value = int(self.data.get(key, 0)) + 1
        self.data[key] = value
        return value

    def expire(self, key, secs):
        self.data[f"ttl:{key}"] = secs

    def zremrangebyscore(self, redis_key, min_score, max_score):
        if redis_key not in self.data:
            return 0
        self.data[redis_key] = [ts for ts in self.data[redis_key] if ts > max_score]
        return len(self.data[redis_key])

    def zcard(self, redis_key):
        return len(self.data.get(redis_key, []))

    def delete(self, redis_key):
        if redis_key in self.data:
            del self.data[redis_key]

    def eval(self, script, num_keys, redis_key, expected_value, ttl_ms=None):
        """Reproduz scripts simples de lock validando o dono informado."""

        stored_value = self.data.get(redis_key)
        if stored_value == expected_value:
            if ttl_ms is not None:
                self.data[f"ttl:{redis_key}"] = ttl_ms / 1000
                return 1
            self.data.pop(redis_key, None)
            return 1

        return 0

@pytest.fixture(autouse=True)
def patch_redis_client(monkeypatch):
    fake_redis = FakeRedis()

    #Redireciona as chamadas de obtenção do cliente Redis para a versão fake
    monkeypatch.setattr("shared.utils.redis_client.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("shared.utils.redis_locks.get_redis_client", lambda: fake_redis, raising=False)
    monkeypatch.setattr(redis_locks_module, "get_redis_client", lambda: fake_redis, raising=False)

    return fake_redis

@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    """ Congela o tempo para simulação precisa """
    monkeypatch.setattr(time, "time", lambda: 0.0)
