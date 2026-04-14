from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

import market_alert.notifications.infra.channels as channels_module
import market_alert.notifications.services.services_notifications as notifications_module
from market_alert.enums.enums_notifications import EventType, NotificationChannel
from market_alert.notifications.evaluator import NotificationCandidate


pytestmark = pytest.mark.unit


class _BeginStub:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _DBStub:
    def begin(self):
        return _BeginStub()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def _candidate() -> NotificationCandidate:
    return NotificationCandidate(
        channel=NotificationChannel.email,
        event_type=EventType.price_change,
        payload={"dispatch_mode": "controlled"},
        priority=1,
        recipient="user@example.com",
        subject="Preco alterado",
        message="O preco mudou.",
    )


def _notification(*, attempts: int = 1, max_attempts: int = 3, cooldown_seconds: int = 60):
    return SimpleNamespace(
        id=uuid4(),
        dedup_hash="dedup-1",
        attempts=attempts,
        max_attempts=max_attempts,
        channel=NotificationChannel.email,
        recipient="user@example.com",
        subject="Preco alterado",
        message="O preco mudou.",
        payload={"dispatch_mode": "controlled"},
        cooldown_seconds=cooldown_seconds,
        monitored_product_id=uuid4(),
        event_log=SimpleNamespace(event_type=EventType.price_change),
    )


def test_persist_candidate_suppresses_when_last_sent_is_within_cooldown(monkeypatch) -> None:
    db = _DBStub()
    monitored = SimpleNamespace(id=uuid4(), user_id=uuid4())
    user = SimpleNamespace(id=uuid4())
    now = datetime.now(timezone.utc)
    acquire_calls: list[tuple[str, int]] = []

    monkeypatch.setattr(notifications_module, "generate_dedup_hash", lambda **kwargs: "dedup-1")
    monkeypatch.setattr(notifications_module, "resolve_cooldown_seconds", lambda **kwargs: 300)
    monkeypatch.setattr(notifications_module, "get_last_sent_at", lambda *args, **kwargs: now - timedelta(seconds=30))
    monkeypatch.setattr(
        notifications_module.notification_lock_manager,
        "acquire",
        lambda dedup_hash, ttl_seconds=60: acquire_calls.append((dedup_hash, ttl_seconds)) or (True, "owner-1"),
    )

    result = notifications_module._persist_candidate(
        db,
        candidate=_candidate(),
        event_id=uuid4(),
        monitored=monitored,
        user=user,
        event_type=EventType.price_change,
        now=now,
    )

    assert result is None
    assert acquire_calls == []


def test_persist_candidate_suppresses_when_lock_is_unavailable(monkeypatch) -> None:
    db = _DBStub()
    monitored = SimpleNamespace(id=uuid4(), user_id=uuid4())
    user = SimpleNamespace(id=uuid4())
    now = datetime.now(timezone.utc)
    created_notifications: list[object] = []

    monkeypatch.setattr(notifications_module, "generate_dedup_hash", lambda **kwargs: "dedup-lock")
    monkeypatch.setattr(notifications_module, "resolve_cooldown_seconds", lambda **kwargs: 120)
    monkeypatch.setattr(notifications_module, "get_last_sent_at", lambda *args, **kwargs: None)
    monkeypatch.setattr(notifications_module.notification_redis_repository, "has_dedup_marker", lambda dedup_hash: False)
    monkeypatch.setattr(
        notifications_module.notification_redis_repository,
        "has_cooldown_marker",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(notifications_module, "has_recent_sent_notification", lambda *args, **kwargs: False)
    monkeypatch.setattr(notifications_module, "has_dedup_in_window", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        notifications_module.notification_lock_manager,
        "acquire",
        lambda dedup_hash, ttl_seconds=60: (False, None),
    )
    monkeypatch.setattr(
        notifications_module,
        "create_notification",
        lambda *args, **kwargs: created_notifications.append(kwargs),
    )

    result = notifications_module._persist_candidate(
        db,
        candidate=_candidate(),
        event_id=uuid4(),
        monitored=monitored,
        user=user,
        event_type=EventType.price_change,
        now=now,
    )

    assert result is None
    assert created_notifications == []


def test_persist_candidate_sets_dedup_marker_persists_and_releases_lock(monkeypatch) -> None:
    db = _DBStub()
    monitored = SimpleNamespace(id=uuid4(), user_id=uuid4())
    user = SimpleNamespace(id=uuid4())
    now = datetime.now(timezone.utc)
    release_calls: list[tuple[str, str | None]] = []
    dedup_markers: list[tuple[str, int]] = []
    notification_id = uuid4()

    monkeypatch.setattr(notifications_module, "generate_dedup_hash", lambda **kwargs: "dedup-create")
    monkeypatch.setattr(notifications_module, "resolve_cooldown_seconds", lambda **kwargs: 180)
    monkeypatch.setattr(notifications_module, "get_last_sent_at", lambda *args, **kwargs: None)
    monkeypatch.setattr(notifications_module.notification_redis_repository, "has_dedup_marker", lambda dedup_hash: False)
    monkeypatch.setattr(
        notifications_module.notification_redis_repository,
        "has_cooldown_marker",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(notifications_module, "has_recent_sent_notification", lambda *args, **kwargs: False)
    monkeypatch.setattr(notifications_module, "has_dedup_in_window", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        notifications_module.notification_lock_manager,
        "acquire",
        lambda dedup_hash, ttl_seconds=60: (True, "owner-create"),
    )
    monkeypatch.setattr(
        notifications_module.notification_lock_manager,
        "release",
        lambda dedup_hash, owner: release_calls.append((dedup_hash, owner)),
    )
    monkeypatch.setattr(
        notifications_module.notification_redis_repository,
        "set_dedup_marker",
        lambda dedup_hash, ttl_seconds: dedup_markers.append((dedup_hash, ttl_seconds)) or True,
    )
    monkeypatch.setattr(
        notifications_module,
        "create_notification",
        lambda *args, **kwargs: SimpleNamespace(id=notification_id),
    )
    monkeypatch.setattr(notifications_module, "update_alert_rule_last_triggered", lambda *args, **kwargs: None)
    monkeypatch.setattr(notifications_module, "update_preference_last_notified", lambda *args, **kwargs: None)

    result = notifications_module._persist_candidate(
        db,
        candidate=_candidate(),
        event_id=uuid4(),
        monitored=monitored,
        user=user,
        event_type=EventType.price_change,
        now=now,
    )

    assert result == str(notification_id)
    assert dedup_markers == [("dedup-create", 180)]
    assert release_calls == [("dedup-create", "owner-create")]


def test_process_notification_marks_sent_and_registers_cooldown(monkeypatch) -> None:
    db = _DBStub()
    notification = _notification(attempts=1, max_attempts=3, cooldown_seconds=90)
    attempts: list[dict[str, object]] = []
    sent_ids: list[object] = []
    cooldown_markers: list[dict[str, object]] = []
    releases: list[tuple[str, str | None]] = []

    monkeypatch.setattr(
        notifications_module,
        "acquire_notification_for_processing",
        lambda db, notification_id: notification,
    )
    monkeypatch.setattr(
        notifications_module.notification_lock_manager,
        "acquire",
        lambda dedup_hash, ttl_seconds=60: (True, "owner-send"),
    )
    monkeypatch.setattr(
        notifications_module.notification_lock_manager,
        "release",
        lambda dedup_hash, owner: releases.append((dedup_hash, owner)),
    )
    monkeypatch.setattr(
        channels_module,
        "get_channel_adapter",
        lambda channel: SimpleNamespace(
            send=lambda payload: {
                "success": True,
                "provider_id": "provider-1",
                "raw_response": {"detail": "queued"},
            }
        ),
    )
    monkeypatch.setattr(
        notifications_module,
        "add_notification_attempt",
        lambda *args, **kwargs: attempts.append(kwargs),
    )
    monkeypatch.setattr(
        notifications_module,
        "mark_notification_sent",
        lambda db, notification, commit=False: sent_ids.append(notification.id),
    )
    monkeypatch.setattr(
        notifications_module.notification_redis_repository,
        "set_cooldown_marker",
        lambda **kwargs: cooldown_markers.append(kwargs) or True,
    )

    result = notifications_module.process_notification(db, notification_id=notification.id)

    assert result is True
    assert attempts[0]["status"].value == "success"
    assert sent_ids == [notification.id]
    assert cooldown_markers[0]["ttl_seconds"] == 90
    assert releases == [("dedup-1", "owner-send")]


def test_process_notification_dead_letters_when_attempts_are_exhausted(monkeypatch) -> None:
    db = _DBStub()
    notification = _notification(attempts=3, max_attempts=3, cooldown_seconds=0)
    dead_lettered: list[object] = []
    failed_marks: list[object] = []

    monkeypatch.setattr(
        notifications_module,
        "acquire_notification_for_processing",
        lambda db, notification_id: notification,
    )
    monkeypatch.setattr(
        notifications_module.notification_lock_manager,
        "acquire",
        lambda dedup_hash, ttl_seconds=60: (True, "owner-dead-letter"),
    )
    monkeypatch.setattr(
        notifications_module.notification_lock_manager,
        "release",
        lambda dedup_hash, owner: None,
    )
    monkeypatch.setattr(
        channels_module,
        "get_channel_adapter",
        lambda channel: SimpleNamespace(
            send=lambda payload: {
                "success": False,
                "error": "provider_down",
                "raw_response": {"detail": "temporary outage"},
            }
        ),
    )
    monkeypatch.setattr(notifications_module, "add_notification_attempt", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        notifications_module,
        "mark_notification_dead_letter",
        lambda db, notification, commit=False: dead_lettered.append(notification.id),
    )
    monkeypatch.setattr(
        notifications_module,
        "mark_notification_failed",
        lambda db, notification, next_attempt_at, commit=False: failed_marks.append(notification.id),
    )

    result = notifications_module.process_notification(db, notification_id=notification.id)

    assert result is False
    assert dead_lettered == [notification.id]
    assert failed_marks == []
