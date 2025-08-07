from types import SimpleNamespace
import asyncio

from app.notifications.manager import NotificationManager
from app.notifications.channels.base import NotificationChannel


class DummyChannel(NotificationChannel):
    async def send_async(self, user, subject: str, message: str) -> dict | None:
        return {}

def test_notification_manager_send_performance(benchmark, patch_rate_limiter, monkeypatch):
    monkeypatch.setattr("alert_app.notifications.manager.create_notification_log", lambda *a, **k: None)
    channels = [DummyChannel() for _ in range(5)]
    manager = NotificationManager(channels)
    user = SimpleNamespace(id="u1", email="user@example.com")
    benchmark(lambda: asyncio.run(manager.send_async(None, user, "subject", "message")))

def test_notification_manager_send_rendered_performance(benchmark, patch_rate_limiter, monkeypatch):
    monkeypatch.setattr("alert_app.notifications.manager.create_notification_log", lambda *a, **k: None)
    channels = [DummyChannel() for _ in range(5)]
    manager = NotificationManager(channels)
    user = SimpleNamespace(id="u1", email="user@example.com")

    def renderer(monitored, alert, html=False):
        return alert.get("msg", "")

    monitored = SimpleNamespace()
    alert = {"msg": "hello"}
    benchmark(manager.send_rendered, None, user, "subject", renderer, monitored, alert)
