from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from shared import metrics

from market_alert.enums.enums_alerts import AlertType
from market_alert.services.services_notifications import dispatch_price_alerts, filter_alerts_by_rules, is_duplicate_notification


class DummyCounter:
    def labels(self, **_kw):
        return self

    def inc(self):
        pass

@pytest.fixture(autouse=True)
def fake_metrics(monkeypatch):
    counter = DummyCounter()
    monkeypatch.setattr(metrics, "ALERT_RULES_TRIGGERED_TOTAL", counter)
    monkeypatch.setattr(metrics, "ALERT_RULES_SUPPRESSED_TOTAL", counter)
    monkeypatch.setattr(metrics, "NOTIFICATIONS_SKIPPED_TOTAL", counter)

def test_filter_alerts_by_rules(monkeypatch):
    monkeypatch.setattr("market_alert.services.services_notifications.alert_matches_rule", lambda a, r: True)
    now = datetime.now(timezone.utc)
    rule = SimpleNamespace(id=1, rule_type=AlertType.PRICE_TARGET, last_notified_at=None)
    alerts = [{"price": 10}]
    resultado = filter_alerts_by_rules(alerts, [rule], 60, now)
    assert len(resultado) == 1
    assert resultado[0][0]["rule_id"] is None

def test_filter_alerts_by_rules_cooldown(monkeypatch):
    monkeypatch.setattr("market_alert.services.services_notifications.alert_matches_rule", lambda a, r: True)
    now = datetime.now(timezone.utc)
    rule = SimpleNamespace(id=1, rule_type=AlertType.PRICE_TARGET, last_notified_at=now)
    alerts = [{"price": 10}]
    resultado = filter_alerts_by_rules(alerts, [rule], 60, now)
    assert resultado == []

def test_is_duplicate_notification(monkeypatch):
    monkeypatch.setattr("market_alert.services.services_notifications.has_recent_duplicate_notification", lambda *a, **k: True)
    assert is_duplicate_notification(object(), 1, "s", "p") is True
    assert is_duplicate_notification(None, 1, "s", "p") is False

def test_dispatch_price_alerts_orquestrador(monkeypatch):
    chamadas = {}

    def fake_filter(alerts, rules, cooldown, now):
        chamadas["filter"] = True
        regra = rules[0]
        return [({**alerts[0], "rule_id": str(regra.id)}, regra)]

    def fake_dup(db, user_id, subject, preview):
        chamadas["dup"] = True
        return False

    class DummyManager:
        def send_rendered(self, *a, **k):
            chamadas["send"] = True

    monkeypatch.setattr("market_alert.services.services_notifications.filter_alerts_by_rules", fake_filter)
    monkeypatch.setattr("market_alert.services.services_notifications.is_duplicate_notification", fake_dup)
    monkeypatch.setattr("market_alert.services.services_notifications.get_user_by_id", lambda db, uid: SimpleNamespace(id=uid, notifications_enabled=True))
    monkeypatch.setattr("market_alert.services.services_notifications.get_alert_rules_or_default",
                        lambda db, uid, pid: [
                            SimpleNamespace(
                                id=1,
                                rule_type=AlertType.PRICE_TARGET,
                                last_notified_at=None,
                            )
                        ],
    )
    monkeypatch.setattr("market_alert.services.services_notifications.render_price_alert", lambda m, a: "preview")
    product = SimpleNamespace(user_id=1, name_identification="Produto")
    dispatch_price_alerts(None, product, [{}], manager=DummyManager())
    assert chamadas == {"filter": True, "dup": True, "send": True}
