from types import SimpleNamespace

from market_alert.notifications.matching import alert_matches_rule
from market_alert.enums.enums_alerts import AlertType
from market_alert.enums.enums_products import ProductStatus


def make_rule(rule_type, status=None):
    return SimpleNamespace(
        rule_type=rule_type,
        product_status=status,
        id="r1"
    )

def test_price_rules_accept_any_change_event():
    rule = make_rule(AlertType.PRICE_CHANGE)
    increase_alert = {"type": "price_increase", "change": 1, "old_price": 10}
    drop_alert = {"type": "price_below_monitored", "price": 5}

    assert alert_matches_rule(increase_alert, rule)
    assert alert_matches_rule(drop_alert, rule)

def test_price_target_behaves_like_price_change_for_compatibility():
    rule = make_rule(AlertType.PRICE_TARGET)
    alert = {"type": "price_decrease", "change": 2}
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

def test_rule_with_product_status_filters_alerts():
    rule = make_rule(AlertType.LISTING_PAUSED, status=ProductStatus.unavailable)
    assert alert_matches_rule({"status": "unavailable"}, rule)
    assert not alert_matches_rule({"status": "removed"}, rule)
