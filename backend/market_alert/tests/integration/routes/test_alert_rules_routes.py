import uuid

from market_alert.models.models_users import User
from market_alert.models.models_alerts import AlertRule
from market_alert.models.models_products import MonitoredProduct
from market_alert.enums.enums_products import MonitoringType, MonitoredStatus
from market_alert.core.password import hash_password
from market_alert.enums.enums_alerts import AlertType
from market_alert.crud.crud_alert_rules import get_alert_rule


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
        rule_type=AlertType.PRICE_CHANGE,
        enabled=True
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)

    response = client.delete(f"/alerts/{rule.id}")
    assert response.status_code == 404

    remaining = get_alert_rule(db_session, rule.id)
    assert remaining is not None

def test_delete_own_rule(client, db_session, test_user, prepare_test_database):
    rule = AlertRule(
        user_id=test_user.id,
        rule_type=AlertType.PRICE_CHANGE,
        enabled=True
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)

    response = client.delete(f"/alerts/{rule.id}")
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
        rule_type=AlertType.PRICE_CHANGE,
        enabled=True
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)

    resp = client.put(f"/alerts/{rule.id}", json={"enabled": False})
    assert resp.status_code == 404

def test_update_own_rule(client, db_session, test_user, prepare_test_database):
    rule = AlertRule(
        user_id=test_user.id,
        rule_type=AlertType.PRICE_CHANGE,
        enabled=True
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)

    resp = client.put(
        f"/alerts/{rule.id}",
        json={"rule_type": AlertType.LISTING_PAUSED.value, "enabled": False}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rule_type"] == AlertType.LISTING_PAUSED.value
    assert data["enabled"] is False

def test_rule_creation_simplified(client, db_session, test_user, prepare_test_database):
    user_id = str(test_user.id)
    resp = client.post("/alerts/", json={})
    assert resp.status_code == 201
    data = resp.json()
    assert data["user_id"] == user_id
    assert data["rule_type"] == AlertType.PRICE_CHANGE.value

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

    resp = client.post("/alerts/", json={"monitored_product_id": str(mp.id)})
    assert resp.status_code == 400
