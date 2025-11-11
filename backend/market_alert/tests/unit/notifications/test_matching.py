from types import SimpleNamespace
from decimal import Decimal

from market_alert.notifications.matching import alert_matches_rule
from market_alert.enums.enums_alerts import AlertType
from market_alert.enums.enums_products import ProductStatus


def make_rule(rule_type, value=None, percent=None, status=None):
    return SimpleNamespace(
        rule_type=rule_type,
        threshold_value=value,
        threshold_percent=percent,
        product_status=status,
        id="r1"
    )

def test_price_target_rule_uses_value_and_percent():
    rule = make_rule(AlertType.PRICE_TARGET, value=10, percent=5)
    alert = {"type": "price_event", "price": 8, "pct_below_monitored": 20}
    assert alert_matches_rule(alert, rule)
    assert alert["pct_below_threshold"] == Decimal("20.00")

    alert = {"type": "price_event", "price": 12, "pct_below_monitored": 20}
    assert not alert_matches_rule(alert, rule)

    alert = {"type": "price_event", "price": 9, "pct_below_monitored": 3}
    assert not alert_matches_rule(alert, rule)

def test_price_change_rule_checks_value_and_percent():
    rule = make_rule(AlertType.PRICE_CHANGE, value=2, percent=10)
    alert = {
        "type": "price_increase",
        "change": 3,
        "old_price": 20
    }
    assert alert_matches_rule(alert, rule)

    alert["change"] = 1
    assert not alert_matches_rule(alert, rule)

    alert = {
        "type": "price_decrease",
        "change": 1,
        "old_price": 30
    }
    rule = make_rule(AlertType.PRICE_CHANGE, percent=5)
    assert not alert_matches_rule(alert, rule)

def test_price_change_rule_only_value_matches():
    rule = make_rule(AlertType.PRICE_CHANGE, value=3)
    alert = {
        "type": "price_decrease",
        "change": 4,
        "old_price": 10
    }
    assert alert_matches_rule(alert, rule)

def test_listing_rules_match_status():
    paused = make_rule(AlertType.LISTING_PAUSED)
    removed = make_rule(AlertType.LISTING_REMOVED)
    assert alert_matches_rule({"status": "unavailable"}, paused)
    assert not alert_matches_rule({"status": "removed"}, paused)
    assert alert_matches_rule({"status": "removed"}, removed)

def test_scraping_error_rule_checks_error_and_detail():
    rule = make_rule(AlertType.SCRAPING_ERROR)
    assert alert_matches_rule({"error": "timeout"}, rule)
    assert alert_matches_rule({"detail": "fail"}, rule)
    assert not alert_matches_rule({}, rule)

def test_rule_with_threshold_value_filters_alerts():
    rule = make_rule(AlertType.PRICE_TARGET, value=5)
    assert alert_matches_rule({"type": "price_event", "price": Decimal("4.00")}, rule)
    assert not alert_matches_rule({"type": "price_event", "price": Decimal("6.00")}, rule)

def test_rule_with_product_status_filters_alerts():
    rule = make_rule(AlertType.LISTING_PAUSED, status=ProductStatus.unavailable)
    assert alert_matches_rule({"status": "unavailable"}, rule)
    assert not alert_matches_rule({"status": "removed"}, rule)
