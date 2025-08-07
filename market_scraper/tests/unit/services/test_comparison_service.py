import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from decimal import Decimal
from alert_app.services.services_comparison import run_price_comparison

def test_run_price_comparison_success(monkeypatch):
    db = Mock()
    mp_id = uuid.uuid4()
    monitored = SimpleNamespace(id=mp_id)
    competitors = [SimpleNamespace(id=uuid.uuid4())]
    result_data = {"ok": True}

    monkeypatch.setattr(
        "alert_app.services.services_comparison.get_monitored_product_by_id",
        lambda db_, mid: monitored
    )
    monkeypatch.setattr(
        "alert_app.services.services_comparison.get_competitors_by_monitored_id",
        lambda db_, mid: competitors
    )
    captured = {}
    def fake_compare(m, c, tolerance=None, price_change_threshold=None):
        captured["tolerance"] = tolerance
        captured["pct"] = price_change_threshold
        return result_data

    monkeypatch.setattr(
        "alert_app.services.services_comparison.compare_prices",
        fake_compare
    )
    created = {}
    def fake_create(db_, mid, data):
        created["mid"] = mid
        created["data"] = data
        return SimpleNamespace()

    monkeypatch.setattr(
        "alert_app.services.services_comparison.create_price_comparison",
        fake_create
    )

    result, alerts = run_price_comparison(db, mp_id)

    assert result is result_data
    assert alerts == result_data.get("alerts", [])
    assert created["mid"] == mp_id
    assert created["data"] == result_data
    assert captured["tolerance"] is not None
    assert captured["pct"] is not None

def test_run_price_comparison_not_found(monkeypatch):
    db = Mock()
    mp_id = uuid.uuid4()

    monkeypatch.setattr(
        "alert_app.services.services_comparison.get_monitored_product_by_id",
        lambda db_, mid: None
    )

    with pytest.raises(ValueError):
        run_price_comparison(db, mp_id)

def test_run_price_comparison_custom_params(monkeypatch):
    db = Mock()
    mp_id = uuid.uuid4()
    monitored = SimpleNamespace(id=mp_id)
    competitors = []

    called = {}
    def fake_compare(m, c, tolerance=None, price_change_threshold=None):
        called["tolerance"] = tolerance
        called["pct"] = price_change_threshold
        return {}

    monkeypatch.setattr(
        "alert_app.services.services_comparison.get_monitored_product_by_id",
        lambda db_, mid: monitored
    )
    monkeypatch.setattr(
        "alert_app.services.services_comparison.get_competitors_by_monitored_id",
        lambda db_, mid: competitors
    )
    monkeypatch.setattr(
        "alert_app.services.services_comparison.compare_prices",
        fake_compare
    )
    monkeypatch.setattr(
        "alert_app.services.services_comparison.create_price_comparison",
        lambda *a, **k: None
    )

    tol = Decimal("0.5")
    thr = Decimal("0.7")
    run_price_comparison(db, mp_id, tolerance=tol, price_change_threshold=thr)

    assert called["tolerance"] == tol
    assert called["pct"] == thr
