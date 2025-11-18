import uuid

import pytest
from pydantic import ValidationError

from market_alert.schemas.schemas_alert_rules import AlertRuleCreate, QuickAlertRuleCreate
from market_alert.enums.enums_alerts import AlertType


def base_data(**k):
    data = {
        "user_id": uuid.uuid4(),
        "rule_type": AlertType.PRICE_CHANGE,
    }
    data.update(k)
    return data

def test_price_change_rule_without_thresholds_is_valid():
    rule = AlertRuleCreate(**base_data())
    assert rule.rule_type == AlertType.PRICE_CHANGE


def test_quick_rule_defaults_to_price_change():
    quick = QuickAlertRuleCreate()
    assert quick.rule_type == AlertType.PRICE_CHANGE

def test_rejects_unsupported_rule_type():
    with pytest.raises(ValidationError):
        AlertRuleCreate(**base_data(rule_type=AlertType.CIRCUIT_BREAKER_OPEN))
        