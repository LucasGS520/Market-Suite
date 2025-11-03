""" Avalia utilitário de cliente Redis, incluindo suspensão de scraping e isolamento por thread """

import threading
import importlib

from shared.utils import redis_client as rc

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
    global rc
    rc = importlib.reload(rc)
    fake = FakeRedis()

    def fake_from_url(url, decode_responses=True):
        return fake

    monkeypatch.setattr(rc.redis.Redis, "from_url", staticmethod(fake_from_url))
    monkeypatch.setattr(rc, "_thread_local", threading.local())

    assert rc.is_scraping_suspended() is False
    rc.suspend_scraping(10)
    assert rc.is_scraping_suspended() is True
    rc.resume_scraping()
    assert rc.is_scraping_suspended() is False

def test_get_redis_client_thread_isolation(monkeypatch):
    global rc
    rc = importlib.reload(rc)

    def fake_from_url(url, decode_responses=True):
        return FakeRedis()

    monkeypatch.setattr(rc.redis.Redis, "from_url", staticmethod(fake_from_url))
    monkeypatch.setattr(rc, "_thread_local", threading.local())

    clients = []

    def target():
        clients.append(rc.get_redis_client())

    threads = [threading.Thread(target=target) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert clients[0] is not clients[1]

def test_get_redis_client_same_thread(monkeypatch):
    global rc
    rc = importlib.reload(rc)

    def fake_from_url(url, decode_responses=True):
        return FakeRedis()

    monkeypatch.setattr(rc.redis.Redis, "from_url", staticmethod(fake_from_url))
    monkeypatch.setattr(rc, "_thread_local", threading.local())

    client1 = rc.get_redis_client()
    client2 = rc.get_redis_client()

    assert client1 is client2
