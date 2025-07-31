from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.tasks.compare_prices_tasks import compare_prices_task

class DummyRedis:
    def set(self, *a, **k):
        pass

class DummySession:
    """ Gerente de contexto simples emulando uma sessão SQLAlchemy """
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        pass


def test_compare_prices_task_success(monkeypatch):
    """ Fluxo completo deve criar registro de comparação """
    mp_id = str(uuid4())
    mp = SimpleNamespace(id=mp_id)
    comps = [SimpleNamespace(id="c1")]
    result = {"lowest_competitor": {}, "highest_competitor": {}, "alerts": []}

    monkeypatch.setattr("app.tasks.compare_prices_tasks.redis_client", DummyRedis())
    monkeypatch.setattr("app.tasks.compare_prices_tasks.SessionLocal", DummySession)

    called = {}

    def fake_run_comparison(db, mid, **kwargs):
        called["mid"] = str(mid)
        called.update(kwargs)
        return result, []

    sent = {}
    def fake_delay(mid, alerts):
        sent["args"] = (mid, alerts)

    monkeypatch.setattr("app.tasks.compare_prices_tasks.send_notification_task.delay", fake_delay)

    monkeypatch.setattr("app.tasks.compare_prices_tasks.run_price_comparison", fake_run_comparison)

    compare_prices_task.run(mp_id)

    assert called["mid"] == mp_id
    assert not sent

def test_compare_prices_task_retry_called(monkeypatch):
    """ Se ocorrer erro durante a execução, a task chama retry """
    mp_id = str(uuid4())
    monkeypatch.setattr("app.tasks.compare_prices_tasks.redis_client", DummyRedis())
    monkeypatch.setattr("app.tasks.compare_prices_tasks.SessionLocal", DummySession)

    def fake_run(*a, **k):
        raise ValueError("err")

    monkeypatch.setattr("app.tasks.compare_prices_tasks.run_price_comparison", fake_run)

    called = {}

    def fake_retry(*a, **k):
        called["exc"] = k.get("exc")
        raise RuntimeError("retry")

    monkeypatch.setattr(compare_prices_task, "retry", fake_retry)

    with pytest.raises(RuntimeError):
        compare_prices_task.run(mp_id)

    assert isinstance(called.get("exc"), Exception)
