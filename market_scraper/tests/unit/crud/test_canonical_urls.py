import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from alert_app.crud import crud_monitored, crud_competitor, crud_alert_rules
from alert_app.schemas.schemas_products import MonitoredProductCreateScraping, MonitoredScrapedInfo, CompetitorProductCreateScraping, CompetitorScrapedInfo


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

    def refresh(self, obj):
        pass

    def rollback(self):
        pass

def test_monitored_url_is_canonicalized(monkeypatch):
    db = DummyDB()
    monkeypatch.setattr(crud_alert_rules, "get_active_alert_rules_for_product", lambda *a, **k: [])
    monkeypatch.setattr(crud_alert_rules, "create_alert_rule", lambda *a, **k: None)

    payload = MonitoredProductCreateScraping(
        name_identification="Prod",
        product_url="https://www.mercadolivre.com.br/MLB-12345-produto?foo=1",
        target_price=Decimal("1.00")
    )
    info = MonitoredScrapedInfo(current_price=Decimal("1.10"), thumbnail=None, free_shipping=False)

    prod = crud_monitored.create_or_update_monitored_product_scraped(
        db, uuid.uuid4(), payload, info, datetime.now(timezone.utc)
    )

    assert prod.product_url == "https://produto.mercadolivre.com.br/MLB-12345"

def test_competitor_url_is_canonicalized():
    db = DummyDB()

    payload = CompetitorProductCreateScraping(
        monitored_product_id=uuid.uuid4(),
        product_url="https://ww.mercadolivre.com.br/MLB-99999-slug#abc",
    )
    info = CompetitorScrapedInfo(
        name="Prod",
        current_price=Decimal("10"),
        old_price=None,
        thumbnail=None,
        free_shipping=False,
        seller=None,
        seller_rating=None
    )

    comp = crud_competitor.create_or_update_competitor_product_scraped(
        db, payload, info, datetime.now(timezone.utc)
    )

    assert comp.product_url == "https://produto.mercadolivre.com.br/MLB-99999"
