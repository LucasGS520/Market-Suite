from app.utils.circuit_breaker import CircuitBreaker


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.ttl_store = {}

    def set(self, key, value, ex=None):
        self.store[key] = value
        if ex:
            self.ttl_store[key] = ex

    def ttl(self, key):
        return self.ttl_store.get(key)

    def incr(self, key):
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def expire(self, key, ex):
        self.ttl_store[key] = ex

    def exists(self, key):
        return key in self.store

    def delete(self, key):
        self.store.pop(key, None)
        self.ttl_store.pop(key, None)

def test_record_failure_performance(benchmark, monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("app.utils.redis_client.get_redis_client", lambda: redis)
    cb = CircuitBreaker(redis=redis)
    benchmark(cb.record_failure, "bench")

def test_record_success_performance(benchmark, monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("app.utils.redis_client.get_redis_client", lambda: redis)
    cb = CircuitBreaker(redis=redis)
    cb.record_failure("bench")
    benchmark(cb.record_success, "bench")
