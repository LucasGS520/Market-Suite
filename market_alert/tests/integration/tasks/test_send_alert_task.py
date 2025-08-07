import pytest
from types import SimpleNamespace

from app.tasks.alert_tasks import send_alert_task
from app.models.models_alerts import NotificationLog
from app.enums.enums_alerts import ChannelType


class DummyDB:
    def __init__(self, log=None, called=None):
        self.log = log
        self.called = called if called is not None else {}

    def get(self, model, pk):
        if model is NotificationLog:
            return self.log
        return None

    def commit(self):
        self.called.setdefault("commit", True)

    def rollback(self):
        self.called.setdefault("rollback", True)

    def close(self):
        self.called.setdefault("closed", True)

def test_send_alert_task_dispatches(monkeypatch):
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

    monkeypatch.setattr("alert_app.tasks.alert_tasks.SessionLocal", lambda: DummyDB(log, called))
    monkeypatch.setattr("alert_app.tasks.alert_tasks.get_user_by_id", lambda db, uid: SimpleNamespace(id=uid))

    def fake_send(self, db, user, subject, message, alert_rule_id=None, alert_type=None):
        called["user"] = user.id
        called["subject"] = subject
        called["db"] = db

    monkeypatch.setattr("alert_app.tasks.alert_tasks.NotificationManager.send", fake_send)

    send_alert_task.run(log.id)

    assert called["user"] == "u1"
    assert called["subject"] == "S"
    assert isinstance(called["db"], DummyDB)
    assert called.get("commit")
    assert called.get("closed")

def test_send_alert_task_retry(monkeypatch):
    called = {}

    class Dummy(DummyDB):
        def __init__(self):
            super().__init__(log=None, called=called)

    monkeypatch.setattr("alert_app.tasks.alert_tasks.SessionLocal", lambda: Dummy())
    monkeypatch.setattr("alert_app.tasks.alert_tasks.NotificationManager.send", lambda self, *a, **k: called.setdefault("send_called", True))

    def fake_retry(*a, **k):
        called["retry"] = True
        raise RuntimeError("retry")

    monkeypatch.setattr(send_alert_task, "retry", fake_retry)

    with pytest.raises(RuntimeError):
        send_alert_task.run("missing")

    assert called.get("retry")
    assert "send_called" not in called
