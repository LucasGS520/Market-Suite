import market_alert.tasks.metrics_tasks as metrics_tasks
from shared.metrics.metrics_cache import CACHE_CLEANUP_TOTAL


class FakeRedis:
    """ Implementação mínima de Redis para simular TTL e varredura de chaves """

    def __init__(self):
        self.store = {}
        self.ttl_map = {}

    def set(self, key, value, ex=None):
        self.store[key] = value
        self.ttl_map[key] = -1 if ex is None else ex

    def ttl(self, key):
        if key not in self.store:
            return -2
        return self.ttl_map.get(key, -1)

    def delete(self, key):
        self.store.pop(key, None)
        self.ttl_map.pop(key, None)

    def scan(self, cursor=0, match=None, count=None):
        import fnmatch

        keys = list(self.store.keys())
        if match:
            keys = [k for k in keys if fnmatch.fnmatch(k, match)]
        return 0, keys

def test_cleanup_cache_remove_expired(monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(metrics_tasks, "redis_client", fake_redis)
    CACHE_CLEANUP_TOTAL._value.set(0)

    fake_redis.set("cache:valida", "1", ex=100)
    fake_redis.set("cache:expirada", "1", ex=0)
    fake_redis.set("cache:sem_ttl", "1")
    fake_redis.set("outra", "1", ex=50)

    metrics_tasks.cleanup_cache.run()

    assert "cache:valida" in fake_redis.store
    assert "cache:expirada" not in fake_redis.store
    assert "cache:sem_ttl" not in fake_redis.store
    assert "outra" in fake_redis.store
    assert CACHE_CLEANUP_TOTAL._value.get() == 2

def test_cleanup_cache_logs_error(monkeypatch):
    class ErroRedis:
        def scan(self, *a, **k):
            raise RuntimeError("boom")

    fake_log = {}
    monkeypatch.setattr(metrics_tasks, "redis_client", ErroRedis())
    monkeypatch.setattr(metrics_tasks.logger, "error", lambda *a, **k: fake_log.setdefault("error", True))

    metrics_tasks.cleanup_cache.run()

    assert fake_log.get("error")
