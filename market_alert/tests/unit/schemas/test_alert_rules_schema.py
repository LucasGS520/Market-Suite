import uuid
from decimal import Decimal
import pytest
from pydantic import ValidationError

from alert_app.schemas.schemas_alert_rules import AlertRuleCreate
from alert_app.enums.enums_alerts import AlertType


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

def test_target_price_positive():
    with pytest.raises(ValidationError):
        AlertRuleCreate(**base_data(target_price=Decimal("-5")))

def test_threshold_percent_bounds():
    with pytest.raises(ValidationError):
        AlertRuleCreate(**base_data(threshold_percent=0))
    with pytest.raises(ValidationError):
        AlertRuleCreate(**base_data(threshold_percent=101))
    AlertRuleCreate(**base_data(threshold_percent=50))
