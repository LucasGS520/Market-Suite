import uuid
from decimal import Decimal

from app.models.models_users import User
from app.models.models_products import MonitoredProduct
from app.models.models_comparisons import PriceComparison
from app.enums.enums_products import MonitoringType, MonitoredStatus
from app.core.password import hash_password

import app.routes.routes_comparisons as rc


def _create_monitored(db_session, user_id):
    mp = MonitoredProduct(
        user_id=user_id,
        name_identification="Prod",
        monitoring_type=MonitoringType.scraping,
        product_url="http://example.com/p",
        target_price=Decimal("1"),
        current_price=Decimal("1"),
        status=MonitoredStatus.active
    )
    db_session.add(mp)
    db_session.commit()
    db_session.refresh(mp)
    return mp

def _create_comparison(db_session, mp_id, idx=1):
    pc = PriceComparison(
        monitored_product_id=mp_id,
        data={"idx": idx}
    )
    db_session.add(pc)
    db_session.commit()
    db_session.refresh(pc)
    return pc

def test_list_comparison(client, db_session, test_user, prepare_test_database):
    mp = _create_monitored(db_session, test_user.id)
    c1 = _create_comparison(db_session, mp.id, 1)
    c2 = _create_comparison(db_session, mp.id, 2)

    resp = client.get(f"/comparisons/{mp.id}")
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()}
    assert ids == {str(c1.id), str(c2.id)}

def test_run_comparison_endpoint(client, db_session, test_user, monkeypatch, prepare_test_database):
    mp = _create_monitored(db_session, test_user.id)
    called = {}

    def fake_run(db, mid, tolerance=None, price_change_threshold=None):
        called["mid"] = str(mid)
        called["tol"] = tolerance
        called["pct"] = price_change_threshold
        return {"ok": True}, []

    monkeypatch.setattr(rc, "run_price_comparison", fake_run)

    resp = client.post(
        f"/comparisons/{mp.id}/run",
        params={"tolerance": 0.5, "price_change_threshold": 0.2}
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert called == {"mid": str(mp.id), "tol": Decimal("0.5"), "pct": Decimal("0.2")}

def test_comparisons_require_owner_or_exist(client, db_session, test_user, prepare_test_database):
    unique = uuid.uuid4().hex[:8]
    other = User(
        id=uuid.uuid4(),
        name="Outro",
        email=f"outro_{unique}@example.com",
        phone_number=f"119{unique}",
        password=hash_password("senha321")
    )
    db_session.add(other)
    db_session.commit()

    mp = _create_monitored(db_session, other.id)
    missing = uuid.uuid4()

    resp = client.get(f"/comparisons/{mp.id}")
    assert resp.status_code == 404

    resp = client.get(f"/comparisons/{missing}")
    assert resp.status_code == 404

    resp = client.post(f"/comparisons/{mp.id}/run")
    assert resp.status_code == 404

    resp = client.post(f"/comparisons/{missing}/run")
    assert resp.status_code == 404
