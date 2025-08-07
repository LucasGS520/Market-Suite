from types import SimpleNamespace

from alert_app.notifications.manager import NotificationManager, dispatch_price_alerts
from alert_app.notifications.channels.base import NotificationChannel
from alert_app.notifications.channels.email import EmailChannel
from alert_app.enums.enums_alerts import ChannelType
from alert_app.enums.enums_alerts import AlertType

class DummyChannel(NotificationChannel):
    def __init__(self, fail: bool = False):
        self.calls = []
        self.fail = fail

    async def send_async(self, user, subject: str, message: str) -> dict | None:
        self.calls.append((user, subject, message))
        if self.fail:
            raise RuntimeError("fail")
        return None

def test_alert_manager_dispatches_to_all_channels(monkeypatch):
    ch1 = DummyChannel()
    ch2 = DummyChannel()
    manager = NotificationManager([ch1, ch2])
    user = SimpleNamespace(id="u1")

    logs = []
    monkeypatch.setattr(
        "alert_app.notifications.manager.create_notification_log",
        lambda db, user_id, channel, subject, message, alert_rule_id=None, alert_type=None, provider_metadata=None, success=True, error=None: logs.append((channel, success, alert_rule_id))
    )

    manager.send(None, user, "subject", "message", alert_rule_id="rule1")

    assert len(ch1.calls) == 1
    assert len(ch2.calls) == 1
    assert [log[0] for log in logs] == [ChannelType.WEBHOOK, ChannelType.WEBHOOK]
    assert all(log[1] for log in logs)
    assert [log[2] for log in logs] == ["rule1", "rule1"]

def test_alert_manager_uses_asyncio_gather(monkeypatch):
    ch1 = DummyChannel()
    ch2 = DummyChannel()
    manager = NotificationManager([ch1, ch2])
    user = SimpleNamespace(id="u1")

    async def fake_gather(*tasks):
        called["count"] = len(tasks)
        return [await t for t in tasks]

    called = {}
    monkeypatch.setattr("alert_app.notifications.manager.asyncio.gather", fake_gather)
    monkeypatch.setattr("alert_app.notifications.manager.create_notification_log", lambda *a, **k: None)

    manager.send(None, user, "s", "m")

    assert called["count"] == 2

def test_alert_manager_logs_errors(monkeypatch):
    ch = DummyChannel(fail=True)
    manager = NotificationManager([ch])
    user = SimpleNamespace(id="u1")

    recorded = {}
    def fake_create(db, user_id, channel, subject, message, alert_rule_id=None, alert_type=None, provider_metadata=None, success=True, error=None):
        recorded["success"] = success
        recorded["error"] = error
        recorded["rule"] = alert_rule_id

    monkeypatch.setattr(
        "alert_app.notifications.manager.create_notification_log",
        fake_create
    )

    manager.send(None, user, "subject", "message", alert_rule_id="rule2")

    assert recorded["success"] is False
    assert "fail" in recorded["error"]
    assert recorded["rule"] == "rule2"

class DummyLogger:
    def __init__(self):
        self.events = []

    def warning(self, *a, **k):
        self.events.append(k)

class DummyCounter:
    def __init__(self):
        self.calls = []

    def labels(self, **k):
        self.kw = k
        return self

    def inc(self):
        self.calls.append(self.kw)

def test_get_notification_manager_logs_missing_settings(monkeypatch):
    from alert_app.notifications import manager as manager_mod
    from alert_app.core.config import settings

    dummy = DummyLogger()
    monkeypatch.setattr(manager_mod, "logger", dummy)
    counter = DummyCounter()
    monkeypatch.setattr(manager_mod.metrics, "NOTIFICATIONS_SKIPPED_TOTAL", counter)

    monkeypatch.setattr(settings, "SMTP_HOST", None)
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", None)
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", None)
    monkeypatch.setattr(settings, "TWILIO_SMS_FROM", None)
    monkeypatch.setattr(settings, "TWILIO_WHATSAPP_FROM", None)
    monkeypatch.setattr(settings, "FCM_SERVER_KEY", None)
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", None)

    manager_mod.get_notification_manager()

    channels = {e["channel"] for e in dummy.events}
    assert {"email", "sms", "whatsapp", "push", "slack"} <= channels
    assert len(counter.calls) == 5

def test_get_notification_manager_no_logs_when_configured(monkeypatch):
    from alert_app.notifications import manager as manager_mod
    from alert_app.core.config import settings

    dummy = DummyLogger()
    monkeypatch.setattr(manager_mod, "logger", dummy)
    counter = DummyCounter()
    monkeypatch.setattr(manager_mod.metrics, "NOTIFICATIONS_SKIPPED_TOTAL", counter)

    monkeypatch.setattr(settings, "SMTP_HOST", "smtp")
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "sid")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setattr(settings, "TWILIO_SMS_FROM", "+1")
    monkeypatch.setattr(settings, "TWILIO_WHATSAPP_FROM", "+2")
    monkeypatch.setattr(settings, "FCM_SERVER_KEY", "key")
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "http://hook")

    class DummyClient:
        def __init__(self, *a, **k):
            pass

    monkeypatch.setattr("alert_app.notifications.channels.sms.AsyncTwilioHttpClient", lambda *a, **k: None)
    monkeypatch.setattr("alert_app.notifications.channels.sms.Client", DummyClient)
    monkeypatch.setattr("alert_app.notifications.channels.whatsapp.AsyncTwilioHttpClient", lambda *a, **k: None)
    monkeypatch.setattr("alert_app.notifications.channels.whatsapp.Client", DummyClient)

    manager_mod.get_notification_manager()

    assert dummy.events == []
    assert counter.calls == []

def test_dispatch_price_alerts_handles_rule_without_id(monkeypatch):
    from alert_app.notifications import manager as manager_mod

    logs = []

    user = SimpleNamespace(id="u1")
    mp = SimpleNamespace(
        id="m1",
        user_id="u1",
        name_identification="Prod"
    )

    rule = SimpleNamespace(
        rule_type=AlertType.PRICE_TARGET,
        threshold_value=5,
        threshold_percent=None,
        enabled=True
    )

    monkeypatch.setattr(manager_mod, "get_user_by_id", lambda *a, **k: user)
    monkeypatch.setattr(manager_mod, "get_notification_manager", lambda: NotificationManager([DummyChannel()]))
    monkeypatch.setattr(manager_mod, "create_notification_log", lambda db, user_id, channel, subject, message,
                        alert_rule_id=None, alert_type=None, provider_metadata=None, success=True, error=None: logs.append(alert_rule_id))
    monkeypatch.setattr(manager_mod, "update_last_notified", lambda *a, **k: None)

    dispatch_price_alerts(None, mp, [{"name": "A", "price": 5}])

    assert logs and logs[0] is None

def test_send_rendered_renders_per_channel(monkeypatch):
    email = EmailChannel()
    email_messages = []

    async def fake_send_email(user, subject, message):
        email_messages.append(message)
        return None

    monkeypatch.setattr(email, "send_async", fake_send_email)

    dummy = DummyChannel()
    logs = []

    def fake_log(db, user_id, channel, subject, message, alert_rule_id=None, alert_type=None, provider_metadata=None, success=True, error=None):
        logs.append(channel)

    monkeypatch.setattr("alert_app.notifications.manager.create_notification_log", fake_log)

    manager = NotificationManager([email, dummy])
    user = SimpleNamespace(id="u1", email="ex@example.com")

    def renderer(monitored, alert, html=False):
        return "html" if html else "text"

    manager.send_rendered(None, user, "Subject", renderer, SimpleNamespace(), {})

    assert email_messages == ["html"]
    assert dummy.calls and dummy.calls[0][2] == "text"
    assert logs == [ChannelType.EMAIL, ChannelType.WEBHOOK]
