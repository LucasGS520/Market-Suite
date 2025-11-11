import uuid
from decimal import Decimal
import pytest
from pydantic import ValidationError

from market_alert.schemas.schemas_alert_rules import AlertRuleCreate, QuickAlertRuleCreate
from market_alert.enums.enums_alerts import AlertType


def base_data(**k):
    data = {
        "user_id": uuid.uuid4(),
        "rule_type": AlertType.PRICE_TARGET,
    }
    data.update(k)
    return data

def test_threshold_value_positive():
    with pytest.raises(ValidationError):
        AlertRuleCreate(**base_data(threshold_value=Decimal("-1")))

def test_price_rule_requires_threshold():
    with pytest.raises(ValidationError):
        AlertRuleCreate(**base_data())

def test_threshold_percent_bounds():
    with pytest.raises(ValidationError):
        AlertRuleCreate(**base_data(threshold_percent=0))
    with pytest.raises(ValidationError):
        AlertRuleCreate(**base_data(threshold_percent=101))
    AlertRuleCreate(**base_data(threshold_percent=50))

def test_quick_rule_requires_threshold():
    with pytest.raises(ValidationError):
        QuickAlertRuleCreate()
        