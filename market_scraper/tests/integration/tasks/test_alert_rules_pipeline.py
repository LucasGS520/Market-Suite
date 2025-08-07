from types import SimpleNamespace
from uuid import uuid4

from alert_app.tasks.compare_prices_tasks import compare_prices_task
from alert_app.tasks import alert_tasks
from alert_app.notifications.manager import NotificationManager
from alert_app.notifications.channels.base import NotificationChannel
from alert_app.enums.enums_alerts import AlertType


class DummyRedis:
    def set(self, *a, **k):
        pass

class DummySession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        pass

def test_alerts_logged_after_comparison(monkeypatch):
    mp_id = str(uuid4())

    monkeypatch.setattr("alert_app.tasks.compare_prices_tasks.redis_client", DummyRedis())
    monkeypatch.setattr("alert_app.tasks.compare_prices_tasks.SessionLocal", DummySession)
    monkeypatch.setattr("alert_app.tasks.alert_tasks.SessionLocal", lambda: DummySession())
    monkeypatch.setattr("alert_app.tasks.alert_tasks.get_monitored_product_by_id", lambda db, pid: SimpleNamespace(id=pid, name_identification="prod", user_id=user.id))

    user = SimpleNamespace(id="u1")
    monkeypatch.setattr("alert_app.notifications.manager.get_user_by_id", lambda db, uid: user)

    sent = []
    class DummyChannel(NotificationChannel):
        async def send_async(self, u, subject, message) -> dict | None:
            sent.append((subject, message))
            return None
    monkeypatch.setattr("alert_app.notifications.manager.get_notification_manager", lambda: NotificationManager([DummyChannel()]))

    logs = []
    monkeypatch.setattr("alert_app.notifications.manager.create_notification_log", lambda db, user_id, channel, subject, message, alert_rule_id=None, alert_type=None, provider_metadata=None, success=True, error=None: logs.append((channel, subject)))
    rule = SimpleNamespace(id="r1", rule_type=AlertType.PRICE_TARGET, threshold_value=6, threshold_percent=None, enabled=True)
    monkeypatch.setattr("alert_app.notifications.manager.get_active_alert_rules_for_product", lambda *a, **k: [rule])
    monkeypatch.setattr("alert_app.notifications.manager.has_recent_duplicate_notification", lambda *a, **k: False)
    monkeypatch.setattr("alert_app.notifications.manager.update_last_notified", lambda *a, **k: None)

    dispatched = {}
    orig_dispatch = alert_tasks.dispatch_price_alerts
    def wrapper(db, mp, alerts):
        dispatched["called"] = True
        return orig_dispatch(db, mp, alerts)
    monkeypatch.setattr(alert_tasks, "dispatch_price_alerts", wrapper)

    def fake_delay(mid, alerts):
        alert_tasks.send_notification_task.run(mid, alerts)
    monkeypatch.setattr(alert_tasks.send_notification_task, "delay", fake_delay)

    def fake_run(db, mid, **kwargs):
        alerts = [
            {"msg": "a", "price": 5, "name": "c"},
            {"msg": "b", "price": 12, "name": "d"}
        ]
        return {
            "lowest_competitor": {},
            "highest_competitor": {},
            "alerts": alerts
        }, alerts
    monkeypatch.setattr("alert_app.tasks.compare_prices_tasks.run_price_comparison", fake_run)

    compare_prices_task.run(mp_id)

    assert len(sent) == 2
    assert logs
    assert dispatched.get("called")
