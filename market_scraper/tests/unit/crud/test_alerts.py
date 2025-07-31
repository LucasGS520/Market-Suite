from types import SimpleNamespace
from datetime import datetime

from app.crud import crud_alert_rules as crud_alerts
from app.enums.enums_products import ProductStatus


def test_update_alert_rule_success(monkeypatch):
    rule = SimpleNamespace(
        id="r1",
        threshold_value=5,
        threshold_percent=None,
        target_price=None,
        product_status=None,
        enabled=True
    )
    db_called = {}

    class DummyDB:
        def commit(self):
            db_called["commit"] = True
        def refresh(self, obj):
            db_called["refresh"] = obj

    db = DummyDB()
    monkeypatch.setattr(crud_alerts, "get_alert_rule", lambda d, rid: rule)

    update = {
        "threshold_value": 10,
        "threshold_percent": 1.5,
        "target_price": 20,
        "product_status": ProductStatus.available
    }

    result = crud_alerts.update_alert_rule(db, "r1", update)

    assert result is rule
    assert rule.threshold_value == 10
    assert rule.threshold_percent == 1.5
    assert rule.target_price == 20
    assert rule.product_status == ProductStatus.available
    assert db_called.get("commit") is True
    assert db_called.get("refresh") is rule

def test_update_alert_rule_missing(monkeypatch):
    db_called = {}
    class DummyDB:
        def commit(self):
            db_called["commit"] = True
        def refresh(self, obj):
            db_called["refresh"] = obj

    db = DummyDB()
    monkeypatch.setattr(crud_alerts, "get_alert_rule", lambda d, rid: None)

    result = crud_alerts.update_alert_rule(db, "r1", {"threshold_value": 10})

    assert result is None
    assert not db_called

def test_update_last_notified(monkeypatch):
    rule = SimpleNamespace(id="r1", last_notified_at=None)
    db_called = {}

    class DummyDB:
        def commit(self):
            db_called["commit"] = True

        def refresh(self, obj):
            db_called["refresh"] = obj

    db = DummyDB()
    monkeypatch.setattr(crud_alerts, "update_alert_rule", lambda d, rid, data: rule.__dict__.update(data) or rule)

    res = crud_alerts.update_last_notified(db, "r1")

    assert res is not None
    assert isinstance(rule.last_notified_at, datetime)

class DummyGauge:
    def __init__(self):
        self.inc_calls = 0
        self.dec_calls = 0

    def inc(self):
        self.inc_calls += 1

    def dec(self):
        self.dec_calls += 1


def test_update_alert_rule_enabled_inc(monkeypatch):
    rule = SimpleNamespace(id="r1", enabled=False)
    db = type("DB", (), {"commit": lambda self: None, "refresh": lambda self, obj: None})()
    gauge = DummyGauge()

    monkeypatch.setattr(crud_alerts, "get_alert_rule", lambda d, rid: rule)
    monkeypatch.setattr(crud_alerts.metrics, "ALERT_RULES_ACTIVE", gauge)

    crud_alerts.update_alert_rule(db, "r1", {"enabled": True})

    assert rule.enabled is True
    assert gauge.inc_calls == 1
    assert gauge.dec_calls == 0

def test_update_alert_rule_enabled_dec(monkeypatch):
    rule = SimpleNamespace(id="r1", enabled=True)
    db = type("DB", (), {"commit": lambda self: None, "refresh": lambda self, obj: None})()
    gauge = DummyGauge()

    monkeypatch.setattr(crud_alerts, "get_alert_rule", lambda d, rid: rule)
    monkeypatch.setattr(crud_alerts.metrics, "ALERT_RULES_ACTIVE", gauge)

    crud_alerts.update_alert_rule(db, "r1", {"enabled": False})

    assert rule.enabled is False
    assert gauge.dec_calls == 1
    assert gauge.inc_calls == 0
