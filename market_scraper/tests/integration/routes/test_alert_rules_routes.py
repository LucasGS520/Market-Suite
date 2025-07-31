import uuid

from app.models.models_users import User
from app.models.models_alerts import AlertRule
from app.models.models_products import MonitoredProduct
from app.enums.enums_products import MonitoringType, MonitoredStatus
from app.core.password import hash_password
from app.enums.enums_alerts import AlertType
from app.crud.crud_alert_rules import get_alert_rule


def test_cannot_delete_other_users_rule(client, db_session, test_user, prepare_test_database):
    other_user = User(
        id=uuid.uuid4(),
        name="Outro",
        email="outro@example.com",
        phone_number="11988888888",
        password=hash_password("senha321"),
    )
    db_session.add(other_user)
    db_session.commit()

    rule = AlertRule(
        user_id=other_user.id,
        rule_type=AlertType.PRICE_TARGET,
        threshold_value=100.0,
        enabled=True
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)

    response = client.delete(f"/alert_rules/{rule.id}")
    assert response.status_code == 404

    remaining = get_alert_rule(db_session, rule.id)
    assert remaining is not None

def test_delete_own_rule(client, db_session, test_user, prepare_test_database):
    rule = AlertRule(
        user_id=test_user.id,
        rule_type=AlertType.PRICE_TARGET,
        threshold_value=50.0,
        enabled=True
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)

    response = client.delete(f"/alert_rules/{rule.id}")
    assert response.status_code == 200

    remaining = get_alert_rule(db_session, rule.id)
    assert remaining is None

def test_cannot_update_other_users_rule(client, db_session, test_user, prepare_test_database):
    other_unique = uuid.uuid4().hex[:8]
    other = User(
        id=uuid.uuid4(),
        name="Outro",
        email="other@example.com",
        phone_number=f"119{other_unique}",
        password=hash_password("senha321")
    )
    db_session.add(other)
    db_session.commit()

    rule = AlertRule(
        user_id=other.id,
        rule_type=AlertType.PRICE_TARGET,
        threshold_value=10.0,
        enabled=True
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)

    resp = client.put(f"/alert_rules/{rule.id}", json={"threshold_value": 20})
    assert resp.status_code == 404

def test_update_own_rule(client, db_session, test_user, prepare_test_database):
    rule = AlertRule(
        user_id=test_user.id,
        rule_type=AlertType.PRICE_TARGET,
        threshold_value=5.0,
        enabled=True
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)

    resp = client.put(
        f"/alert_rules/{rule.id}",
        json={"threshold_value": 8.0, "enabled": False}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["threshold_value"] == "8.00"
    assert data["enabled"] is False

def test_rule_creation_simplified(client, db_session, test_user, prepare_test_database):
    user_id = str(test_user.id)
    resp = client.post("/alert_rules/", json={"threshold_value": 12})
    assert resp.status_code == 201
    data = resp.json()
    assert data["user_id"] == user_id
    assert data["rule_type"] == AlertType.PRICE_TARGET.value
    assert data["threshold_value"] == "12.00"

def test_rule_creation_validates_product(client, db_session, test_user, prepare_test_database):
    other_unique = uuid.uuid4().hex[:8]
    other = User(
        id=uuid.uuid4(),
        name="Outra pessoa",
        email="outra@example.com",
        phone_number=f"119{other_unique}",
        password=hash_password("senha321")
    )
    db_session.add(other)
    db_session.commit()

    mp = MonitoredProduct(
        user_id=other.id,
        name_identification="Prod",
        monitoring_type=MonitoringType.scraping,
        product_url="http://example.com/prod",
        status=MonitoredStatus.active
    )
    db_session.add(mp)
    db_session.commit()
    db_session.refresh(mp)

    resp = client.post("/alert_rules/", json={"monitored_product_id": str(mp.id), "threshold_value": 1})
    assert resp.status_code == 400
