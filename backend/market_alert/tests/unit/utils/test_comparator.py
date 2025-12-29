from decimal import Decimal
from types import SimpleNamespace

from backend.market_alert.utils.price_comparator import compare_prices, calculate_discrepancies

def test_compare_prices_no_competitors():
    monitored = SimpleNamespace(id="m1", current_price=Decimal("10.00"))
    result = compare_prices(monitored, [])

    assert result["lowest_competitor"] is None
    assert result["highest_competitor"] is None
    assert result["average_competitor_price"] is None
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

def test_all_competitors_without_price_returns_empty():
    monitored = SimpleNamespace(id="m1", current_price=Decimal("10.00"))
    c1 = SimpleNamespace(id="c1", name_competitor="A", current_price=None)
    c2 = SimpleNamespace(id="c2", name_competitor="B", current_price=None)

    result = compare_prices(monitored, [c1, c2])

    assert result["lowest_competitor"] is None
    assert result["highest_competitor"] is None
    assert result["average_competitor_price"] is None
    assert result["discrepancies"] == []

def test_calculate_discrepancies_helper():
    competitor = SimpleNamespace(id="c1", name_competitor="A", current_price=Decimal("8.00"), old_price=Decimal("9.00"))
    info = calculate_discrepancies(competitor, Decimal("10.00"), Decimal("8.00"), Decimal("0.01"))
    assert info["competitor_id"] == "c1"
    assert info["delta_x_min_competitor"] == Decimal("0.00")
    assert info["delta_x_monitored"] == Decimal("-2.00")
    assert info["pct_below_monitored"] == Decimal("20.00")
