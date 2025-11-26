from decimal import Decimal
from types import SimpleNamespace

from market_alert.utils.comparator import compare_prices, calculate_discrepancies
from market_alert.enums.enums_products import ProductStatus

def test_compare_prices_no_competitors():
    monitored = SimpleNamespace(id="m1", current_price=Decimal("10.00"))
    result = compare_prices(monitored, [])

    assert result["lowest_competitor"] is None
    assert result["highest_competitor"] is None
    assert result["average_competitor_price"] is None
    assert result["alerts"] == []
    assert result["discrepancies"] == []

def test_compare_prices_with_competitors():
    monitored = SimpleNamespace(id="m1", current_price=Decimal("10.00"))
    c1 = SimpleNamespace(id="c1", name_competitor="A", current_price=Decimal("8.00"))
    c2 = SimpleNamespace(id="c2", name_competitor="B", current_price=Decimal("12.00"))

    result = compare_prices(monitored, [c1, c2])

    assert result["lowest_competitor"]["competitor_id"] == "c1"
    assert result["highest_competitor"]["price"] == Decimal("12.00")
    assert result["average_competitor_price"] == Decimal("10.00")
    assert result["lowest_competitor"]["delta_x_monitored"] == Decimal("-2.00")
    assert result["highest_competitor"]["delta_x_monitored"] == Decimal("2.00")
    assert len(result["discrepancies"]) == 2
    assert "delta_x_monitored" in result["discrepancies"][0]
    price_alerts = [
        a for a in result["alerts"] if a.get("type") == "price_below_monitored"
    ]
    assert len(price_alerts) == 1
    assert price_alerts[0]["competitor_id"] == "c1"
    assert price_alerts[0]["pct_below_monitored"] == Decimal("20.00")

def test_competitor_without_price_ignored():
    monitored = SimpleNamespace(id="m1", current_price=Decimal("10.00"))
    c1 = SimpleNamespace(id="c1", name_competitor="A", current_price=None)
    c2 = SimpleNamespace(id="c2", name_competitor="B", current_price=Decimal("12.00"))

    result = compare_prices(monitored, [c1, c2])

    assert result["lowest_competitor"]["competitor_id"] == "c2"
    assert result["highest_competitor"]["competitor_id"] == "c2"
    assert result["average_competitor_price"] == Decimal("12.00")
    assert len(result["discrepancies"]) == 1
    assert "delta_x_monitored" in result["discrepancies"][0]
    assert result["discrepancies"][0]["competitor_id"] == "c2"
    assert result["alerts"] == []

def test_all_competitors_without_price_returns_empty():
    monitored = SimpleNamespace(id="m1", current_price=Decimal("10.00"))
    c1 = SimpleNamespace(id="c1", name_competitor="A", current_price=None)
    c2 = SimpleNamespace(id="c2", name_competitor="B", current_price=None)

    result = compare_prices(monitored, [c1, c2])

    assert result["lowest_competitor"] is None
    assert result["highest_competitor"] is None
    assert result["average_competitor_price"] is None
    assert result["discrepancies"] == []
    assert result["alerts"] == []

def test_price_change_detection():
    monitored = SimpleNamespace(id="m1", current_price=Decimal("10.00"), status=ProductStatus.available)
    c1 = SimpleNamespace(id="c1", name_competitor="A", current_price=Decimal("8.00"), status=ProductStatus.unavailable)

    result = compare_prices(monitored, [c1])

    listing_alerts = [a for a in result["alerts"] if a.get("type") == "listing_status"]
    assert listing_alerts and listing_alerts[0]["status"] == "unavailable"
    assert any(a.get("type") == "price_below_monitored" for a in result["alerts"])

def test_listing_status_alert():
    monitored = SimpleNamespace(id="m1", current_price=Decimal("10.00"), status=ProductStatus.available)
    c1 = SimpleNamespace(id="c1", name_competitor="A", current_price=Decimal("12.00"), old_price=Decimal("12.00"), status=ProductStatus.unavailable)

    result = compare_prices(monitored, [c1])

    assert any(a.get("status") == "unavailable" for a in result["alerts"])

def test_calculate_discrepancies_helper():
    competitor = SimpleNamespace(id="c1", name_competitor="A", current_price=Decimal("8.00"), old_price=Decimal("9.00"))
    info = calculate_discrepancies(competitor, Decimal("10.00"), Decimal("8.00"), Decimal("0.01"))
    assert info["competitor_id"] == "c1"
    assert info["delta_x_min_competitor"] == Decimal("0.00")
    assert info["delta_x_monitored"] == Decimal("-2.00")
    assert info["pct_below_monitored"] == Decimal("20.00")
