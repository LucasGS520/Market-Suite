import pytest
import time


#FakeRedis universal para testes unitários
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

@pytest.fixture(autouse=True)
def patch_redis_client(monkeypatch):
    fake_redis = FakeRedis()

    #Redireciona as chamadas de obtenção do cliente Redis para a versão fake
    monkeypatch.setattr("shared.utils.redis_client.get_redis_client", lambda: fake_redis)

    return fake_redis

@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    """ Congela o tempo para simulação precisa """
    monkeypatch.setattr(time, "time", lambda: 0.0)
