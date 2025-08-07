"""Fixtures comuns para benchmarks de desempenho

Este arquivo define variáveis de ambiente mínimas para que
o módulo de configuração do aplicativo possa ser importado
sem erros durante a coleta de benchmark. Os valores
são espaços reservados e só devem ser utilizados para
os testes de desempenho.
"""

import os
import pytest
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///benchmark.db")
os.environ.setdefault("SECRET_KEY", "benchmark-secret")

from alert_app.utils.rate_limiter import RateLimiter

class FakeRedis:
    def __init__(self):
        self.data = {}
        self.scripts = {}

    def script_load(self, source):
        sha = f"fake-sha-{len(self.scripts)}"
        self.scripts[sha] = source
        return sha

    def set(self, key, value, ex=None):
        self.data[key] = value
        if ex:
            self.data[f"ttl:{key}"] = ex

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

@pytest.fixture(autouse=True)
def patch_rate_limiter(monkeypatch):
    fake_redis = FakeRedis()

    def fake_init(self, redis_key: str, max_requests: int, window_seconds: int):
        self.redis = fake_redis
        self.key = redis_key
        self.limit = max_requests
        self.window = window_seconds
        self.window_ms = window_seconds * 1000
        self.lua_sha = "fake-sha"

    monkeypatch.setattr(RateLimiter, "__init__", fake_init)
    monkeypatch.setattr("alert_app.utils.redis_client.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("scraper_app.utils.intelligent_cache.get_redis_client", lambda: fake_redis)
    return fake_redis

@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 0.0)
