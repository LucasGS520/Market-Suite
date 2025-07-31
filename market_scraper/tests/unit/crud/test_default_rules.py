import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.crud import crud_user, crud_monitored, crud_alert_rules
from app.models.models_users import User
from app.schemas.schemas_users import UserCreate
from app.schemas.schemas_products import MonitoredProductCreateScraping, MonitoredScrapedInfo
from app.enums.enums_alerts import AlertType


class DummyQuery:
    def __init__(self, result=None):
        self._result = result

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._result


class DummyDB:
    def __init__(self):
        self.obj = None

    def query(self, model):
        return DummyQuery(None)

    def add(self, obj):
        self.obj = obj

    def commit(self):
        if getattr(self.obj, "id", None) is None:
            self.obj.id = uuid.uuid4()
        if getattr(self.obj, "created_date", None) is None:
            self.obj.created_date = datetime.now(timezone.utc)
        if getattr(self.obj, "updated_date", None) is None:
            self.obj.updated_date = datetime.now(timezone.utc)

    def refresh(self, obj):
        pass
    def rollback(self):
        pass


def test_default_rule_on_user_creation(monkeypatch):
    called = {}
    db = DummyDB()
    monkeypatch.setattr(User, "set_password", lambda self, pw: setattr(self, "password", b"hash"))
    monkeypatch.setattr(crud_alert_rules, "create_alert_rule", lambda d, data: called.setdefault("rule", data))

    payload = UserCreate(
        name="Teste",
        email="t@example.com",
        phone_number="11999999999",
        password="password1",
        notifications_enabled=True
    )

    user = crud_user.create_user(db, payload)

    rule = called.get("rule")
    assert rule is not None
    assert rule.user_id == user.id
    assert rule.rule_type == AlertType.PRICE_TARGET
    assert rule.enabled is True

def test_default_rule_on_product_creation(monkeypatch):
    called = {}
    db = DummyDB()

    monkeypatch.setattr(crud_alert_rules,"get_active_alert_rules_for_product", lambda d, uid, pid: [])
    monkeypatch.setattr(crud_alert_rules, "create_alert_rule", lambda d, data: called.setdefault("rule", data))

    payload = MonitoredProductCreateScraping(
        name_identification="Prod",
        product_url="http://example.com",
        target_price=Decimal("1.00")
    )
    info = MonitoredScrapedInfo(current_price=Decimal("1.10"), thumbnail=None, free_shipping=False)

    product = crud_monitored.create_or_update_monitored_product_scraped(
        db, uuid.uuid4(), payload, info, datetime.now(timezone.utc)
    )

    rule = called.get("rule")
    assert rule is not None
    assert rule.rule_type == AlertType.PRICE_TARGET
    assert rule.enabled is True
