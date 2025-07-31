import pytest
import time

from app.utils.rate_limiter import RateLimiter

#FakeRedis universal para testes unitarios
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
def patch_rate_limiter(monkeypatch):
    """ Substitui a classe Redis por uma fake e evitar conexão real com redis e leitura de arquivo Lua """
    fake_redis = FakeRedis()

    def fake_init(self, redis_key: str, max_requests: int, window_seconds: int):
        self.redis = fake_redis
        self.key = redis_key
        self.limit = max_requests
        self.window = window_seconds
        self.window_ms = window_seconds * 1000
        self.lua_sha = "fake-sha"

    monkeypatch.setattr(RateLimiter, "__init__", fake_init)
    monkeypatch.setattr("app.utils.redis_client.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("app.utils.circuit_breaker.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("app.utils.robots_txt.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(
        "app.utils.robots_txt.requests.get",
        lambda *a, **k: type("Resp", (), {"status_code": 200, "text": ""})()
    )
    monkeypatch.setattr("app.services.services_scraper_common.redis_client", fake_redis, raising=False)
    monkeypatch.setattr("app.utils.intelligent_cache.get_redis_client", lambda: fake_redis)
    #Garante que o cache inteligente use FakeRedis criado
    import app.services.services_cache_scraper as cache_scraper
    monkeypatch.setattr(cache_scraper.cache_manager, "redis", fake_redis)

    class DummyCircuitBreaker:
        def allow_request(self, *a, **k):
            return True

        def record_success(self, *a, **k):
            pass

        def record_failure(self, *a, **k):
            pass

    monkeypatch.setattr("app.services.services_scraper_common.CircuitBreaker", lambda: DummyCircuitBreaker())

    return fake_redis

@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    """ Congela o tempo para simulação precisa """
    monkeypatch.setattr(time, "time", lambda: 0.0)
