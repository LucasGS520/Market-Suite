from types import SimpleNamespace
from datetime import datetime, timezone, timedelta
import httpx

from app.notifications.channels.email import EmailChannel
from app.notifications.manager import get_notification_manager, dispatch_price_alerts
from app.enums.enums_alerts import AlertType
from tests.unit.utils.test_audit_logger import DummyLogger


class DummyCounter:
    def __init__(self):
        self.calls = []

    def labels(self, **k):
        self.kw = k
        return self

    def inc(self):
        self.calls.append(self.kw)

def test_email_channel_warns_when_missing_email(monkeypatch):
    sent = []

    class DummySMTP:
        def __init__(self, *a, **k):
            pass

        async def connect(self):
            pass

        async def starttls(self):
            pass

        async def login(self, u, p):
            pass

        async def send_message(self, msg):
            sent.append(msg)

        async def quit(self):
            pass

    monkeypatch.setattr("app.notifications.channels.email.aiosmtplib.SMTP", DummySMTP)
    counter = DummyCounter()
    monkeypatch.setattr("app.notifications.channels.email.metrics.NOTIFICATIONS_SKIPPED_TOTAL", counter)
    channel = EmailChannel()
    user = SimpleNamespace(id="u1")

    channel.send(user, "s", "m")

    assert sent == []
    assert counter.calls and counter.calls[0]["reason"] == "email_missing"

def test_get_notification_manager_returns_new_instance(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", None)
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", None)
    monkeypatch.setattr(settings, "TWILIO_SMS_FROM", None)
    monkeypatch.setattr(settings, "TWILIO_WHATSAPP_FROM", None)

    m1 = get_notification_manager()
    m2 = get_notification_manager()
    assert m1 is not m2

def test_dispatch_price_alerts_uses_manager(monkeypatch):
    sent = []

    class DummyManager:
        def send_rendered(self, db, user, subject, renderer, monitored, alert, alert_rule_id=None, alert_type=None):
            msg = renderer(monitored, alert)
            sent.append((db, user, subject, msg, alert_rule_id))

    dummy_user = SimpleNamespace(id="u1")
    monkeypatch.setattr("app.notifications.manager.get_user_by_id", lambda db, uid: dummy_user)
    monkeypatch.setattr("app.notifications.manager.get_notification_manager", lambda: DummyManager())
    monkeypatch.setattr("app.notifications.manager.get_alert_rules_or_default", lambda db, user_id, mid: [])

    monitored = SimpleNamespace(id="m1", user_id="u1", name_identification="Prod")
    alerts = [{"name": "Shop", "price": 10}, {"name": "Shop2", "price": 5 }]

    dispatch_price_alerts(None, monitored, alerts)

    assert sent == []

def test_dispatch_price_alerts_skips_when_no_rules(monkeypatch):
    captured = {}

    class DummyManager:
        def send_rendered(self, db, user, subject, renderer, monitored, alert, alert_rule_id=None, alert_type=None):
            captured['message'] = renderer(monitored, alert)

    dummy_user = SimpleNamespace(id="u1")
    monkeypatch.setattr("app.notifications.manager.get_user_by_id", lambda db, uid: dummy_user)
    monkeypatch.setattr("app.notifications.manager.get_notification_manager", lambda: DummyManager())
    monkeypatch.setattr("app.notifications.manager.get_alert_rules_or_default", lambda db, user_id, mid: [])

    monitored = SimpleNamespace(id="m1", user_id="u1", name_identification="Prod")
    alert = {"name": "Shop", "price": 12.0, "old_price": 10.0, "change": 2.0, "type": "price_increase"}

    dispatch_price_alerts(None, monitored, [alert])

    assert captured == {}

def test_dispatch_price_alerts_filters_by_rules(monkeypatch):
    sent = []

    class DummyManager:
        def send_rendered(self, db, user, subject, renderer, monitored, alert, alert_rule_id=None, alert_type=None):
            sent.append(renderer(monitored, alert))

    user = SimpleNamespace(id="u1")
    rule = SimpleNamespace(
        id="r1",
        rule_type=AlertType.PRICE_TARGET,
        threshold_value=6,
        threshold_percent=None,
        enabled=True
    )

    monkeypatch.setattr("app.notifications.manager.get_user_by_id", lambda db, uid: user)
    monkeypatch.setattr("app.notifications.manager.get_notification_manager", lambda: DummyManager())
    monkeypatch.setattr("app.notifications.manager.get_alert_rules_or_default", lambda db, user_id, mid: [rule])
    monkeypatch.setattr("app.notifications.manager.has_recent_duplicate_notification", lambda *a, **k: False)

    mp = SimpleNamespace(user_id="u1", name_identification="Prod", id="m1")
    alerts = [
        {"name": "A", "price": 5},
        {"name": "B", "price": 12, "old_price": 10, "change": 2, "type": "price_increase"},
    ]

    dispatch_price_alerts(None, mp, alerts)

    assert len(sent) == 1
    assert "A" in sent[0]

def test_dispatch_price_alerts_skips_duplicates(monkeypatch):
    sent = []

    class DummyManager:
        def send_rendered(self, db, user, subject, renderer, monitored, alert, alert_rule_id=None, alert_type=None):
            sent.append(renderer(monitored, alert))

    user = SimpleNamespace(id="u1")
    rule = SimpleNamespace(
        id="r1",
        rule_type=AlertType.PRICE_TARGET,
        threshold_value=None,
        threshold_percent=None,
        enabled=True
    )

    monkeypatch.setattr("app.notifications.manager.get_user_by_id", lambda db, uid: user)
    monkeypatch.setattr("app.notifications.manager.get_notification_manager", lambda: DummyManager())
    monkeypatch.setattr("app.notifications.manager.get_alert_rules_or_default", lambda db, user_id, mid: [rule])
    monkeypatch.setattr("app.notifications.manager.has_recent_duplicate_notification", lambda *a, **k: True)

    mp = SimpleNamespace(user_id="u1", name_identification="Prod", id="m1")
    alert = {"name": "A", "price": 5}

    dispatch_price_alerts(SimpleNamespace(), mp, [alert])

    assert sent == []

def test_dispatch_price_alerts_respects_user_setting(monkeypatch):
    sent = []

    class DummyManager:
        def send_rendered(self, *a, **k):
            sent.append(1)

    user = SimpleNamespace(id="u1", notifications_enabled=False)
    rule = SimpleNamespace(
        id="r1",
        rule_type=AlertType.PRICE_TARGET,
        threshold_value=None,
        threshold_percent=None,
        enabled=True
    )

    monkeypatch.setattr("app.notifications.manager.get_user_by_id", lambda *a, **k: user)
    monkeypatch.setattr("app.notifications.manager.get_notification_manager", lambda: DummyManager())
    monkeypatch.setattr("app.notifications.manager.get_alert_rules_or_default", lambda *a, **k: [rule])
    monkeypatch.setattr("app.notifications.manager.has_recent_duplicate_notification", lambda *a, **k: False)
    counter = DummyCounter()
    monkeypatch.setattr("app.notifications.manager.metrics.NOTIFICATIONS_SKIPPED_TOTAL", counter)

    mp = SimpleNamespace(user_id="u1", name_identification="Prod", id="m1")
    alert = {"name": "A", "price": 5}

    dispatch_price_alerts(SimpleNamespace(), mp, [alert])

    assert sent == []
    assert counter.calls and counter.calls[0]["reason"] == "disabled"

def test_dispatch_price_alerts_respects_cooldown(monkeypatch):
    sent = []

    class DummyManager:
        def send_rendered(self, *a, **k):
            sent.append(1)

    user = SimpleNamespace(id="u1")
    now = datetime.now(timezone.utc)
    rule = SimpleNamespace(
        id="r1",
        rule_type=AlertType.PRICE_TARGET,
        threshold_value=None,
        threshold_percent=None,
        enabled=True,
        last_notified_at=now
    )

    monkeypatch.setattr("app.notifications.manager.get_user_by_id", lambda *a, **k: user)
    monkeypatch.setattr("app.notifications.manager.get_notification_manager", lambda: DummyManager())
    monkeypatch.setattr("app.notifications.manager.get_alert_rules_or_default", lambda *a, **k: [rule])
    monkeypatch.setattr("app.notifications.manager.has_recent_duplicate_notification", lambda *a, **k: False)
    monkeypatch.setattr("app.notifications.manager.settings", SimpleNamespace(ALERT_DUPLICATE_WINDOW=60, ALERT_RULE_COOLDOWN=3600))

    mp = SimpleNamespace(user_id="u1", name_identification="Prod", id="m1")
    alert = {"name": "A", "price": 5}

    dispatch_price_alerts(SimpleNamespace(), mp, [alert])

    assert sent == []

def test_dispatch_price_alerts_updates_timestamp(monkeypatch):
    sent = []

    class DummyManager:
        def send_rendered(self, *a, **k):
            sent.append(1)

    user = SimpleNamespace(id="u1")
    past = datetime.now(timezone.utc) - timedelta(seconds=7200)
    rule = SimpleNamespace(
        id="r1",
        rule_type=AlertType.PRICE_TARGET,
        threshold_value=None,
        threshold_percent=None,
        enabled=True,
        last_notified_at=past
    )
    updated = {}

    monkeypatch.setattr("app.notifications.manager.get_user_by_id", lambda *a, **k: user)
    monkeypatch.setattr("app.notifications.manager.get_notification_manager", lambda: DummyManager())
    monkeypatch.setattr("app.notifications.manager.get_alert_rules_or_default", lambda *a, **k: [rule])
    monkeypatch.setattr("app.notifications.manager.has_recent_duplicate_notification", lambda *a, **k: False)
    monkeypatch.setattr("app.notifications.manager.settings", SimpleNamespace(ALERT_DUPLICATE_WINDOW=60, ALERT_RULE_COOLDOWN=3600))
    def fake_update(db, rid, when):
        updated["time"] = when
    monkeypatch.setattr("app.notifications.manager.update_last_notified", fake_update)

    mp = SimpleNamespace(user_id="u1", name_identification="Prod", id="m1")
    alert = {"name": "A", "price": 5}

    dispatch_price_alerts(SimpleNamespace(), mp, [alert])

    assert sent
    assert "time" in updated and isinstance(updated["time"], datetime)

def test_slack_channel_posts_message(monkeypatch):
    from app.notifications.channels.slack import SlackChannel

    posted = {}

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def post(self, url, json=None, timeout=None):
            posted["url"] = url
            posted["json"] = json
            posted["timeout"] = timeout
            class Resp(SimpleNamespace):
                def raise_for_status(self):
                    pass

            return Resp(status_code=200)

    monkeypatch.setattr("app.notifications.channels.slack.httpx.AsyncClient", DummyClient)

    channel = SlackChannel("http://hook")
    channel.send(SimpleNamespace(id="u1"), "Subject", "Message")

    assert posted["url"] == "http://hook"
    assert posted["json"] == {"text": "*Subject*\nMessage"}
    assert posted["timeout"] == 5

def test_slack_channel_handles_http_error(monkeypatch):
    from app.notifications.channels import slack as slack_mod
    from app.notifications.channels.slack import SlackChannel

    dummy = DummyLogger()
    monkeypatch.setattr(slack_mod, "logger", dummy)

    class DummyResponse:
        def __init__(self, status_code=500):
            self.status_code = status_code

        def raise_for_status(self):
            raise httpx.HTTPError("boom")

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def post(self, url, json=None, timeout=None):
            return DummyResponse()

    monkeypatch.setattr(slack_mod.httpx, "AsyncClient", DummyClient)

    channel = SlackChannel("http://hook")
    res = channel.send(SimpleNamespace(id="u1"), "Subject", "Message")

    assert res is None
    assert dummy.called

def test_push_channel_handles_http_error(monkeypatch):
    from app.notifications.channels import push as push_mod
    from app.notifications.channels.push import PushChannel
    from app.core.config import settings

    dummy = DummyLogger()
    monkeypatch.setattr(push_mod, "logger", dummy)
    monkeypatch.setattr(settings, "FCM_SERVER_KEY", "key")

    class DummyResponse:
        def __init__(self, status_code=500):
            self.status_code = status_code

        def raise_for_status(self):
            raise httpx.HTTPError("boom")

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def post(self, url, json=None, headers=None, timeout=None):
            return DummyResponse()

    monkeypatch.setattr(push_mod.httpx, "AsyncClient", DummyClient)

    user = SimpleNamespace(id="u1", fcm_token="t")
    res = PushChannel().send(user, "Subject", "Message")

    assert res is None
    assert dummy.called

def test_get_notification_manager_includes_slack(monkeypatch):
    from app.notifications.manager import get_notification_manager
    from app.core.config import settings

    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "http://hook")

    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", None)
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", None)
    monkeypatch.setattr(settings, "TWILIO_SMS_FROM", None)
    monkeypatch.setattr(settings, "TWILIO_WHATSAPP_FROM", None)

    manager = get_notification_manager()
    names = [ch.__class__.__name__ for ch in manager.channels]

    assert "SlackChannel" in names

def test_sms_channel_missing_phone_increments_counter(monkeypatch):
    from app.notifications.channels import sms as sms_mod
    from app.notifications.channels.sms import SMSChannel
    from app.core.config import settings

    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "sid")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setattr(settings, "TWILIO_SMS_FROM", "+1")
    monkeypatch.setattr(sms_mod, "AsyncTwilioHttpClient", lambda *a, **k: None)

    class DummyClient:
        def __init__(self, *a, **k):
            self.messages = SimpleNamespace(create_async=lambda *a, **k: None)

    monkeypatch.setattr(sms_mod, "Client", lambda *a, **k: DummyClient())
    counter = DummyCounter()
    monkeypatch.setattr(sms_mod.metrics, "NOTIFICATIONS_SKIPPED_TOTAL", counter)

    channel = SMSChannel()
    user = SimpleNamespace(id="u1")

    channel.send(user, "s", "m")

    assert counter.calls and counter.calls[0]["reason"] == "phone_missing"

def test_whatsapp_channel_missing_number_increments_counter(monkeypatch):
    from app.notifications.channels import whatsapp as wa_mod
    from app.notifications.channels.whatsapp import WhatsAppChannel
    from app.core.config import settings

    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "sid")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setattr(settings, "TWILIO_WHATSAPP_FROM", "+2")
    monkeypatch.setattr(wa_mod, "AsyncTwilioHttpClient", lambda *a, **k: None)

    class DummyClient:
        def __init__(self, *a, **k):
            self.messages = SimpleNamespace(create_async=lambda *a, **k: None)

    monkeypatch.setattr(wa_mod, "Client", lambda *a, **k: DummyClient())
    counter = DummyCounter()
    monkeypatch.setattr(wa_mod.metrics, "NOTIFICATIONS_SKIPPED_TOTAL", counter)

    channel = WhatsAppChannel()
    user = SimpleNamespace(id="u1")

    channel.send(user, "s", "m")

    assert counter.calls and counter.calls[0]["reason"] == "phone_missing"

def test_push_channel_missing_token_increments_counter(monkeypatch):
    from app.notifications.channels import push as push_mod
    from app.notifications.channels.push import PushChannel
    from app.core.config import settings

    monkeypatch.setattr(settings, "FCM_SERVER_KEY", "key")
    counter = DummyCounter()
    monkeypatch.setattr(push_mod.metrics, "NOTIFICATIONS_SKIPPED_TOTAL", counter)

    user = SimpleNamespace(id="u1")
    PushChannel().send(user, "s", "m")

    assert counter.calls and counter.calls[0]["reason"] == "push_token_missing"

def test_slack_channel_missing_webhook_increments_counter(monkeypatch):
    from app.notifications.channels import slack as slack_mod
    from app.notifications.channels.slack import SlackChannel
    from app.core.config import settings

    counter = DummyCounter()
    monkeypatch.setattr(slack_mod.metrics, "NOTIFICATIONS_SKIPPED_TOTAL", counter)
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", None)
    channel = SlackChannel(None)
    channel.send(SimpleNamespace(id="u1"), "s", "m")

    assert counter.calls and counter.calls[0]["reason"] == "slack_webhook_missing"

def test_email_channel_missing_provider_skips(monkeypatch):
    from app.notifications.channels import email as email_mod
    from app.notifications.channels.email import EmailChannel
    from app.core.config import settings

    called = {}
    def dummy_smtp(*a, **k):
        called["init"] = True
        class DummySMTP:
            async def connect(self):
                called["connect"] = True
            async def starttls(self):
                called["starttls"] = True
            async def login(self, u, p):
                called["login"] = True
            async def send_message(self, msg):
                called["send"] = True
            async def quit(self):
                called["quit"] = True
        return DummySMTP()
    monkeypatch.setattr(email_mod.aiosmtplib, "SMTP", dummy_smtp)

    counter = DummyCounter()
    monkeypatch.setattr(email_mod.metrics, "NOTIFICATIONS_SKIPPED_TOTAL", counter)
    monkeypatch.setattr(settings, "SMTP_HOST", None)

    user = SimpleNamespace(id="u1", email="e@example.com")
    EmailChannel().send(user, "s", "m")

    assert called == {}
    assert counter.calls and counter.calls[0]["reason"] == "smtp_not_configured"

def test_sms_channel_missing_provider_skips(monkeypatch):
    from app.notifications.channels import sms as sms_mod
    from app.notifications.channels.sms import SMSChannel
    from app.core.config import settings

    called = {}
    def dummy_http_client(*a, **k):
        called["http_client"] = True
    class DummyClient:
        def __init__(self, *a, **k):
            called["client"] = True
            self.messages = SimpleNamespace(create_async=lambda *a, **k: called.setdefault("send", True))
    monkeypatch.setattr(sms_mod, "AsyncTwilioHttpClient", dummy_http_client)
    monkeypatch.setattr(sms_mod, "Client", lambda *a, **k: DummyClient())

    counter = DummyCounter()
    monkeypatch.setattr(sms_mod.metrics, "NOTIFICATIONS_SKIPPED_TOTAL", counter)
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", None)
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", None)
    monkeypatch.setattr(settings, "TWILIO_SMS_FROM", "+1")

    channel = SMSChannel()
    user = SimpleNamespace(id="u1", phone_number="123")
    channel.send(user, "s", "m")

    assert called == {}
    assert counter.calls and counter.calls[0]["reason"] == "twilio_not_configured"

def test_whatsapp_channel_missing_provider_skips(monkeypatch):
    from app.notifications.channels import whatsapp as wa_mod
    from app.notifications.channels.whatsapp import WhatsAppChannel
    from app.core.config import settings

    called = {}
    def dummy_http_client(*a, **k):
        called["http_client"] = True
    class DummyClient:
        def __init__(self, *a, **k):
            called["client"] = True
            self.messages = SimpleNamespace(create_async=lambda *a, **k: called.setdefault("send", True))
    monkeypatch.setattr(wa_mod, "AsyncTwilioHttpClient", dummy_http_client)
    monkeypatch.setattr(wa_mod, "Client", lambda *a, **k: DummyClient())

    counter = DummyCounter()
    monkeypatch.setattr(wa_mod.metrics, "NOTIFICATIONS_SKIPPED_TOTAL", counter)
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", None)
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", None)
    monkeypatch.setattr(settings, "TWILIO_WHATSAPP_FROM", "+2")

    channel = WhatsAppChannel()
    user = SimpleNamespace(id="u1", whatsapp_number="123")
    channel.send(user, "s", "m")

    assert called == {}
    assert counter.calls and counter.calls[0]["reason"] == "twilio_not_configured"

def test_push_channel_missing_provider_skips(monkeypatch):
    from app.notifications.channels import push as push_mod
    from app.notifications.channels.push import PushChannel
    from app.core.config import settings

    called = {}
    def dummy_client(*a, **k):
        called["client"] = True
        class Dummy:
            async def __aenter__(self):
                called["enter"] = True
                return self
            async def __aexit__(self, exc_type, exc, tb):
                pass
            async def post(self, *a, **k):
                called["post"] = True
                return SimpleNamespace(status_code=200, raise_for_status=lambda: None)
        return Dummy()
    monkeypatch.setattr(push_mod.httpx, "AsyncClient", dummy_client)

    counter = DummyCounter()
    monkeypatch.setattr(push_mod.metrics, "NOTIFICATIONS_SKIPPED_TOTAL", counter)
    monkeypatch.setattr(settings, "FCM_SERVER_KEY", None)

    user = SimpleNamespace(id="u1", fcm_token="t")
    PushChannel().send(user, "s", "m")

    assert called == {}
    assert counter.calls and counter.calls[0]["reason"] == "fcm_not_configured"
