from datetime import datetime, timezone, timedelta

from app.models.models_alerts import NotificationLog, AlertRule
from app.enums.enums_alerts import ChannelType, AlertType


def _create_logs(db_session, user_id):
    rule = AlertRule(
        user_id=user_id,
        rule_type=AlertType.PRICE_TARGET,
        threshold_value=10,
        enabled=True
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)

    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    logs = [
        NotificationLog(
            user_id=user_id,
            alert_rule_id=rule.id,
            channel=ChannelType.EMAIL,
            subject="a",
            message="1",
            sent_at=base,
            success=True
        ),
        NotificationLog(
            user_id=user_id,
            channel=ChannelType.SMS,
            subject="b",
            message="2",
            sent_at=base + timedelta(days=1),
            success=False
        ),
        NotificationLog(
            user_id=user_id,
            channel=ChannelType.EMAIL,
            subject="c",
            message="3",
            sent_at=base + timedelta(days=2),
            success=True
        )
    ]
    db_session.add_all(logs)
    db_session.commit()
    return rule, logs


def test_notification_log_filters(client, db_session, test_user, prepare_test_database):
    rule, logs = _create_logs(db_session, test_user.id)
    rule_id = str(rule.id)

    resp = client.get("/notifications/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert [l["subject"] for l in data] == ["c", "b", "a"]

    resp = client.get("/notifications/logs", params={"limit": 1, "offset": 1})
    assert [l["subject"] for l in resp.json()] == ["b"]

    start = logs[1].sent_at.isoformat()
    resp = client.get("/notifications/logs", params={"start": start})
    assert [l["subject"] for l in resp.json()] == ["c", "b"]

    end = logs[1].sent_at.isoformat()
    resp = client.get("/notifications/logs", params={"end": end})
    assert [l["subject"] for l in resp.json()] == ["b", "a"]

    resp = client.get("/notifications/logs", params={"channel": ChannelType.SMS.value})
    assert [l["subject"] for l in resp.json()] == ["b"]

    resp = client.get("/notifications/logs", params={"success": False})
    assert [l["subject"] for l in resp.json()] == ["b"]

    resp = client.get("/notifications/logs", params={"alert_rule_id": rule_id})
    assert [l["subject"] for l in resp.json()] == ["a"]
