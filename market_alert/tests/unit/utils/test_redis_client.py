from types import SimpleNamespace
from utils import redis_client as rc


class FakeRedis:
    def __init__(self):
        self.store = {}

    def set(self, key, val, ex=None):
        self.store[key] = val

    def exists(self, key):
        return 1 if key in self.store else 0

    def delete(self, key):
        self.store.pop(key, None)


def test_suspend_resume(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(rc, "_redis_client", fake)
    monkeypatch.setattr(rc, "get_redis_client", lambda: fake)

    assert rc.is_scraping_suspended() is False
    rc.suspend_scraping(10)

    assert rc.is_scraping_suspended() is True
    rc.resume_scraping()

    assert rc.is_scraping_suspended() is False