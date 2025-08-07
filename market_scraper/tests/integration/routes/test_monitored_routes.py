import uuid
from decimal import Decimal

from alert_app.models.models_users import User
from alert_app.models.models_products import MonitoredProduct
from alert_app.enums.enums_products import MonitoringType, MonitoredStatus
from alert_app.core.password import hash_password


# --- /monitored/scrape ---
def test_scrape_schedules_task(client, test_user, monkeypatch, prepare_test_database):
    called = {}

    def fake_delay(url, user_id, name_identification, target_price):
        called["url"] = url
        called["user_id"] = user_id
        called["name"] = name_identification
        called["price"] = target_price

    import app.routes.routes_monitored as routes

    monkeypatch.setattr(routes.collect_product_task, "delay", fake_delay)

    payload = {
        "name_identification": "Produto",
        "product_url": "http://example.com/MLB-1234",
        "target_price": "10.00"
    }

    resp = client.post("monitored/scrape", json=payload)
    assert resp.status_code == 400
    assert called == {}


# --- List & Get ---
def _create_product(db, user, name="Prod", url="http://example.com/item"):
    mp = MonitoredProduct(
        user_id=user.id,
        name_identification=name,
        monitoring_type=MonitoringType.scraping,
        product_url=url,
        target_price=Decimal("1.00"),
        current_price=Decimal("1.00"),
        status=MonitoredStatus.active
    )
    db.add(mp)
    db.commit()
    db.refresh(mp)
    return mp

def test_list_and_get_products(client, db_session, test_user, prepare_test_database):
    unique = uuid.uuid4().hex[:8]
    other = User(
        id=uuid.uuid4(),
        name="Outro",
        email=f"outro_{unique}@example.com",
        phone_number=f"119{unique}",
        password=hash_password("senha123")
    )
    db_session.add(other)
    db_session.commit()

    own = _create_product(db_session, test_user, name="Own")
    other_p = _create_product(db_session, other, name="Other")
    own_id = str(own.id)
    other_id = str(other_p.id)

    resp = client.get("/monitored/")
    assert resp.status_code == 200
    data = resp.json()
    assert [p["id"] for p in data] == [str(own.id)]

    resp = client.get(f"/monitored/{own_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(own.id)

    resp = client.get(f"/monitored/{other_id}")
    assert resp.status_code == 404

def test_delete_product_permissions(client, db_session, test_user, prepare_test_database):
    unique = uuid.uuid4().hex[:8]
    other = User(
        id=uuid.uuid4(),
        name="Outro",
        email=f"outro2_{unique}@example.com",
        phone_number=f"119{unique}",
        password=hash_password("senha321")
    )
    db_session.add(other)
    db_session.commit()

    own = _create_product(db_session, test_user, name="OwnDel", url="http://example.com/del1")
    other_p = _create_product(db_session, other, name="OtherDel", url="http://example.com/del2")
    own_id = str(own.id)
    other_id = str(other_p.id)

    resp = client.delete(f"/monitored/{other_id}")
    assert resp.status_code == 404
    from uuid import UUID
    assert db_session.query(MonitoredProduct).filter_by(id=UUID(other_id)).first() is not None

    resp = client.delete(f"/monitored/{own_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == own_id
    assert db_session.query(MonitoredProduct).filter_by(id=UUID(own_id)).first() is None
