import uuid

from alert_app.models.models_products import MonitoredProduct, CompetitorProduct
from alert_app.models.models_users import User
from alert_app.enums.enums_products import MonitoringType, MonitoredStatus, ProductStatus
from alert_app.core.password import hash_password

import alert_app.routes.routes_competitors as rc


def _create_monitored(db_session, user_id):
    mp = MonitoredProduct(
        user_id=user_id,
        name_identification="Prod",
        monitoring_type=MonitoringType.scraping,
        product_url="http://example.com/prod",
        status=MonitoredStatus.active
    )
    db_session.add(mp)
    db_session.commit()
    db_session.refresh(mp)
    return mp

def test_competitor_scrape_schedules_task(client, db_session, test_user, monkeypatch, prepare_test_database):
    mp = _create_monitored(db_session, test_user.id)

    called = {}
    def fake_delay(monitored_product_id=None, url=None):
        called["args"] = (monitored_product_id, url)

    monkeypatch.setattr(rc.collect_competitor_task, "delay", fake_delay)

    payload = {
        "monitored_product_id": str(mp.id),
        "product_url": "http://example.com/MLB-9999"
    }
    resp = client.post("/competitors/scrape", json=payload)
    assert resp.status_code == 400
    assert called == {}

def test_list_competitors(client, db_session, test_user, prepare_test_database):
    mp = _create_monitored(db_session, test_user.id)

    c1 = CompetitorProduct(
        monitored_product_id=mp.id,
        name_competitor="c1",
        product_url="http://example.com/c1",
        current_price=10.0,
        status=ProductStatus.available
    )
    c2 = CompetitorProduct(
        monitored_product_id=mp.id,
        name_competitor="c2",
        product_url="http://example.com/c2",
        current_price=20.0,
        status=ProductStatus.available
    )
    db_session.add_all([c1, c2])
    db_session.commit()

    resp = client.get(f"/competitors/{mp.id}")
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["id"] for item in data}
    assert ids == {str(c1.id), str(c2.id)}

def test_delete_competitors(client, db_session, test_user, prepare_test_database):
    mp = _create_monitored(db_session, test_user.id)
    mp_id = mp.id

    c = CompetitorProduct(
        monitored_product_id=mp.id,
        name_competitor="Del",
        product_url="http://example.com/del",
        current_price=5.0,
        status=ProductStatus.available
    )
    db_session.add(c)
    db_session.commit()

    resp = client.delete(f"/competitors/{mp_id}")
    assert resp.status_code == 200
    remaining = db_session.query(CompetitorProduct).filter_by(monitored_product_id=mp_id).all()
    assert remaining == []

def test_competitor_requires_owner(client, db_session, test_user, prepare_test_database):
    unique = uuid.uuid4().hex[:8]
    other = User(
        id=uuid.uuid4(),
        name="Outro",
        email=f"outro_{unique}@example.com",
        phone_number=f"119{unique}",
        password=hash_password("s")
    )
    db_session.add(other)
    db_session.commit()

    mp = _create_monitored(db_session, other.id)
    mp_id = mp.id
    comp = CompetitorProduct(
        monitored_product_id=mp.id,
        name_competitor="No",
        product_url="http://example.com/no",
        current_price=1.0,
        status=ProductStatus.available
    )
    db_session.add(comp)
    db_session.commit()
    comp_id = comp.id

    resp = client.get(f"/competitors/{mp_id}")
    assert resp.status_code == 404

    resp = client.delete(f"/competitors/{mp_id}")
    assert resp.status_code == 404
    assert db_session.query(CompetitorProduct).filter_by(id=comp_id).first() is not None
