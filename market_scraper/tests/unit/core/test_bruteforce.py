from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from alert_app.core import bruteforce
from alert_app.core.celery_app import monitor_exchange
from alert_app.core.config import settings
from tests.integration.conftest import client


class FakeRedis:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def incr(self, key):
        self.data[key] = int(self.data.get(key, 0)) + 1
        return self.data[key]

    def expire(self, key, ttl):
        pass

    def delete(self, key):
        self.data.pop(key, None)


def make_request(ip="1.1.1.1"):
    return SimpleNamespace(client=SimpleNamespace(host=ip))


def test_block_ip_when_limit_exceeded(monkeypatch):
    fake = FakeRedis()
    fake.data[f"bf:1.1.1.1"] = str(settings.BRUTE_FORCE_MAX_ATTEMPTS)
    monkeypatch.setattr(bruteforce, "redis_client", fake)
    with pytest.raises(HTTPException):
        bruteforce.block_ip(make_request())


def test_record_and_reset(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(bruteforce, "redis_client", fake)
    req = make_request()
    bruteforce.record_failed_attempt(req)
    assert fake.data[f"bf:{req.client.host}"] == 1
    bruteforce.reset_failed_attempts(req)
    assert f"bf:{req.client.host}" not in fake.data
