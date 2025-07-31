import pytest
from types import SimpleNamespace

from app.tasks.alert_tasks import send_notification_task, dispatch_price_alert_task


class DummySession:
    def __init__(self, called: dict):
        self.called = called

    def close(self):
        self.called.setdefault("closed", True)

def test_send_notification_task_dispatches(monkeypatch):
    called = {}
    monkeypatch.setattr("app.tasks.alert_tasks.SessionLocal", lambda: DummySession(called))

    mid = "123e4567-e89b-12d3-a456-426614174000"
    monitored = SimpleNamespace(id=mid, user_id="u1", name_identification="prod")
    monkeypatch.setattr("app.tasks.alert_tasks.get_monitored_product_by_id", lambda db, pid: monitored)

    def dummy_dispatch(db, mp, alerts):
        called["monitored"] = mp.id
        called["alerts"] = alerts
        called["db"] = db

    monkeypatch.setattr("app.tasks.alert_tasks.dispatch_price_alerts", dummy_dispatch)
    monkeypatch.setattr("app.notifications.manager.NotificationManager.send", lambda *a, **k: None)

    alerts = [{"type": "price", "payload": {"a": 1}}]
    send_notification_task.run(mid, alerts)

    assert called["monitored"] == mid
    assert called["alerts"] == alerts
    assert isinstance(called.get("db"), DummySession)
    assert called.get("closed")

def test_send_notification_task_retry(monkeypatch):
    called = {}
    monkeypatch.setattr("app.tasks.alert_tasks.SessionLocal", lambda: DummySession(called))
    monkeypatch.setattr("app.tasks.alert_tasks.get_monitored_product_by_id", lambda db, pid: None)
    monkeypatch.setattr("app.tasks.alert_tasks.dispatch_price_alerts", lambda *a, **k: called.setdefault("dispatched", True))
    monkeypatch.setattr("app.notifications.manager.NotificationManager.send", lambda *a, **k: None)

    def fake_retry(*a, **k):
        called["retry"] = True
        raise RuntimeError("retry")

    monkeypatch.setattr(send_notification_task, "retry", fake_retry)
    with pytest.raises(RuntimeError):
        send_notification_task.run("123e4567-e89b-12d3-a456-426614174999", [])

    assert called.get("retry")
    assert "dispatched" not in called

def test_dispatch_price_alert_task_dispatches(monkeypatch):
    called = {}
    monkeypatch.setattr("app.tasks.alert_tasks.SessionLocal", lambda: DummySession(called))

    mid = "123e4567-e89b-12d3-a456-426614174000"
    monitored = SimpleNamespace(id=mid, user_id="u1", name_identification="prod")
    monkeypatch.setattr("app.tasks.alert_tasks.get_monitored_product_by_id", lambda db, pid: monitored)

    def dummy_dispatch(db, mp, alerts):
        called["monitored"] = mp.id
        called["alerts"] = alerts
        called["db"] = db

    monkeypatch.setattr("app.tasks.alert_tasks.dispatch_price_alerts", dummy_dispatch)
    monkeypatch.setattr("app.notifications.manager.NotificationManager.send", lambda *a, **k: None)

    alert = {"type": "price", "payload": {"a": 1}}
    dispatch_price_alert_task.run(mid, alert)

    assert called["monitored"] == mid
    assert called["alerts"] == [alert]
    assert isinstance(called.get("db"), DummySession)
    assert called.get("closed")

def test_dispatch_price_alert_task_retry(monkeypatch):
    called = {}
    monkeypatch.setattr("app.tasks.alert_tasks.SessionLocal", lambda: DummySession(called))
    monkeypatch.setattr("app.tasks.alert_tasks.get_monitored_product_by_id", lambda db, pid: None)
    monkeypatch.setattr("app.tasks.alert_tasks.dispatch_price_alerts", lambda *a, **k: called.setdefault("dispatched", True))
    monkeypatch.setattr("app.notifications.manager.NotificationManager.send", lambda *a, **k: None)

    def fake_retry(*a, **k):
        called["retry"] = True
        raise RuntimeError("retry")

    monkeypatch.setattr(dispatch_price_alert_task, "retry", fake_retry)
    with pytest.raises(RuntimeError):
        dispatch_price_alert_task.run("123e4567-e89b-12d3-a456-426614174999", {})

    assert called.get("retry")
    assert "dispatched" not in called
