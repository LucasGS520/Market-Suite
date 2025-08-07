import pytest
from types import SimpleNamespace
from app.tasks.alert_tasks import send_alert_task, send_notification_task, dispatch_price_alert_task
from app.models.models_alerts import NotificationLog
from app.enums.enums_alerts import ChannelType


def test_notification_task_success(monkeypatch):
    called = {}
    fake_db = SimpleNamespace(close=lambda: called.setdefault("closed", True))
    monkeypatch.setattr("alert_app.tasks.alert_tasks.SessionLocal", lambda: fake_db)
    mid = "123e4567-e89b-12d3-a456-426614174000"
    monitored = SimpleNamespace(id=mid, user_id="u1", name_identification="prod")
    monkeypatch.setattr(
        "alert_app.tasks.alert_tasks.get_monitored_product_by_id",
        lambda db, pid: monitored
    )

    def dummy_dispatch(db, mp, alerts):
        called["monitored"] = mp.id
        called["alerts"] = alerts
        called["db"] = db

    monkeypatch.setattr("alert_app.tasks.alert_tasks.dispatch_price_alerts", dummy_dispatch)

    alerts = [{"type": "price", "payload": {"a": 1}}]
    send_notification_task.run(monitored.id, alerts)

    assert called["monitored"] == monitored.id
    assert called["alerts"] == alerts
    assert called["db"] is fake_db
    assert called.get("closed")

def test_send_notification_task_retry(monkeypatch):
    fake_db = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr("alert_app.tasks.alert_tasks.SessionLocal", lambda: fake_db)
    monkeypatch.setattr(
        "alert_app.tasks.alert_tasks.get_monitored_product_by_id",
        lambda db, pid: None
    )
    called = {}
    monkeypatch.setattr("alert_app.tasks.alert_tasks.dispatch_price_alerts", lambda *a, **k: called.setdefault("dispatched", True))

    def fake_retry(*a, **k):
        called["retry"] = True
        raise RuntimeError("retry")
    monkeypatch.setattr(send_notification_task, "retry", fake_retry)
    mid = "123e4567-e89b-12d3-a456-426614174000"
    with pytest.raises(RuntimeError):
        send_notification_task.run(mid, [])

    assert called.get("retry")
    assert "dispatched" not in called

def test_dispatch_price_alert_task_success(monkeypatch):
    called = {}
    fake_db = SimpleNamespace(close=lambda: called.setdefault("closed", True))
    monkeypatch.setattr("alert_app.tasks.alert_tasks.SessionLocal", lambda: fake_db)
    mid = "123e4567-e89b-12d3-a456-426614174000"
    monitored = SimpleNamespace(id=mid, user_id="u1", name_identification="prod")
    monkeypatch.setattr(
        "alert_app.tasks.alert_tasks.get_monitored_product_by_id",
        lambda db, pid: monitored
    )

    def dummy_dispatch(db, mp, alerts):
        called["monitored"] = mp.id
        called["alerts"] = alerts
        called["db"] = db

    monkeypatch.setattr("alert_app.tasks.alert_tasks.dispatch_price_alerts", dummy_dispatch)

    alert = {"type": "price", "payload": {"a": 1}}
    dispatch_price_alert_task.run(monitored.id, alert)

    assert called["monitored"] == monitored.id
    assert called["alerts"] == [alert]
    assert called["db"] is fake_db
    assert called.get("closed")

def test_dispatch_price_alert_task_retry(monkeypatch):
    fake_db = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr("alert_app.tasks.alert_tasks.SessionLocal",lambda: fake_db)
    monkeypatch.setattr(
        "alert_app.tasks.alert_tasks.get_monitored_product_by_id",
        lambda db, pid: None
    )
    called = {}
    monkeypatch.setattr("alert_app.tasks.alert_tasks.dispatch_price_alerts", lambda *a, **k: called.setdefault("dispatched", True))

    def fake_retry(*a, **k):
        called["retry"] = True
        raise RuntimeError("retry")

    monkeypatch.setattr(dispatch_price_alert_task, "retry", fake_retry)
    mid = "123e4567-e89b-12d3-a456-426614174000"
    with pytest.raises(RuntimeError):
        dispatch_price_alert_task.run(mid, {})

    assert called.get("retry")
    assert "dispatched" not in called

def test_send_alert_task_success(monkeypatch):
    log = SimpleNamespace(
        id="123e4567-e89b-12d3-a456-426614174000",
        user_id="u1",
        alert_rule_id=None,
        alert_type=None,
        channel=ChannelType.EMAIL,
        subject="S",
        message="M",
        success=False,
        error=None,
        sent_at=None
    )
    called = {}

    class DummyDB:
        def get(self, model, pk):
            if model is NotificationLog:
                return log
            return None

        def commit(self):
            called["commit"] = True

        def rollback(self):
            called["rollback"] = True

        def close(self):
            called["closed"] = True

    monkeypatch.setattr("alert_app.tasks.alert_tasks.SessionLocal", lambda: DummyDB())
    monkeypatch.setattr("alert_app.tasks.alert_tasks.get_user_by_id", lambda db, uid: SimpleNamespace(id=uid))

    def fake_send(self, db_, user, subject, message, alert_rule_id=None, alert_type=None):
        called["user"] = user.id
        called["subject"] = subject
        called["db"] = db_

    monkeypatch.setattr("alert_app.tasks.alert_tasks.NotificationManager.send", fake_send)

    send_alert_task.run(log.id)

    assert called["user"] == "u1"
    assert called["subject"] == "S"
    assert isinstance(called["db"], DummyDB)
    assert called.get("commit")

def test_send_alert_task_retry(monkeypatch):
    class DummyDB:
        def get(self, model, pk):
            return None

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr("alert_app.tasks.alert_tasks.SessionLocal", lambda: DummyDB())

    called = {}

    def fake_retry(*a, **k):
        called["retry"] = True
        raise RuntimeError("retry")

    monkeypatch.setattr(send_alert_task, "retry", fake_retry)

    with pytest.raises(RuntimeError):
        send_alert_task.run("missing")

    assert called.get("retry")
