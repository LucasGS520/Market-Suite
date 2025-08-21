""" Testes do heartbeats nas tasks de monitoramento """

from types import SimpleNamespace
import time
import pytest

from market_alert.tasks import monitor_tasks


class DummySession:
    """ Contexto de sessão fictício """
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

@pytest.mark.parametrize(
    "task,key",
    [
        (monitor_tasks.recheck_monitored_products, "beat:last_scraping"),
        (monitor_tasks.recheck_competitor_products, "beat:last_competitor"),
    ],
)
def test_heartbeat_expire(monkeypatch, fake_redis_client, task, key):
    """ Garante que o heartbeat criado expira automaticamente no Redis """
    fake_redis = fake_redis_client

    monkeypatch.setattr(monitor_tasks, "HEARTBEAT_TTL_SECONDS", 1)
    monkeypatch.setattr(monitor_tasks, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(monitor_tasks, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(monitor_tasks, "get_products_by_type", lambda db, mt: [])
    monkeypatch.setattr(monitor_tasks, "get_all_competitor_products", lambda db: [])

    async def fake_parse(_):
        return []

    monkeypatch.setattr(monitor_tasks, "_parse_monitored_batch", fake_parse)
    monkeypatch.setattr(monitor_tasks, "_parse_competitor_batch", fake_parse)
    monkeypatch.setattr(monitor_tasks, "compare_prices_task", SimpleNamespace(delay=lambda *a, **k: None))
    monkeypatch.setattr(monitor_tasks, "SCRAPING_LATENCY_SECONDS", SimpleNamespace(labels=lambda **k: SimpleNamespace(observe=lambda x: None)))

    tempo = [0]
    monkeypatch.setattr(time, "time", lambda: tempo[0])

    task.run()
    assert fake_redis.exists(key)

    tempo[0] = 2
    assert fake_redis.get(key) is None
    assert not fake_redis.exists(key)
