import pytest
import time

#FakeRedis universal para testes unitarios
class FakeRedis:
    def __init__(self):
        self.data = {}
        self.scripts = {}
        self.expiry = {}

    def script_load(self, source):
        sha = f"fake-sha-{len(self.scripts)}"
        self.scripts[sha] = source
        return sha

    def _cleanup(self, key):
        if key in self.expiry and time.time() >= self.expiry[key]:
            self.expiry.pop(key, None)
            self.data.pop(key, None)

    def set(self, key, value, ex=None):
        self.data[key] = value
        if ex is not None:
            self.expiry[key] = time.time() + ex
        elif key in self.expiry:
            self.expiry.pop(key, None)

    def get(self, key):
        self._cleanup(key)
        return self.data.get(key)

    def exists(self, key):
        self._cleanup(key)
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
        if key in self.data:
            self.expiry[key] = time.time() + secs
            return True
        return False

    def ttl(self, key):
        self._cleanup(key)
        if key not in self.data:
            return -2
        if key not in self.expiry:
            return -1
        return int(self.expiry[key] - time.time())


    def zremrangebyscore(self, redis_key, min_score, max_score):
        if redis_key not in self.data:
            return 0
        self.data[redis_key] = [ts for ts in self.data[redis_key] if ts > max_score]
        return len(self.data[redis_key])

    def zcard(self, redis_key):
        return len(self.data.get(redis_key, []))
    
    def eval(self, script, num_keys, redis_key, owner_id):
        current_value = self.data.get(redis_key)
        if current_value == owner_id:
            del self.data[redis_key]
            return 1
        return 0

    def delete(self, redis_key):
        if redis_key in self.data:
            del self.data[redis_key]

@pytest.fixture(autouse=True)
def fake_redis_client(monkeypatch):
    """ Substitui a cliente Redis por uma implementação em memória """
    fake_redis = FakeRedis()

    monkeypatch.setattr("shared.utils.redis_client.get_redis_client", lambda: fake_redis)
    
    try:
        import market_alert.tasks.scraper_tasks as scraper_tasks
    except ImportError:
        scraper_tasks = None
    if scraper_tasks is not None:
        monkeypatch.setattr(scraper_tasks, "redis_client", fake_redis, raising=False)

    try:
        import backend.market_alert.tasks.recheck_scheduler_task as recheck_scheduler_task
    except ImportError:
        recheck_scheduler_task = None
    if recheck_scheduler_task is not None:
        monkeypatch.setattr(recheck_scheduler_task, "redis_client", fake_redis, raising=False)
    return fake_redis

@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    """ Congela o tempo para simulação precisa """
    monkeypatch.setattr(time, "time", lambda: 0.0)
