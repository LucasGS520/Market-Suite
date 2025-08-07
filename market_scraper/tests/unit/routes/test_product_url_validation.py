import types
import pytest
from fastapi import HTTPException, status

import alert_app.routes.routes_monitored as rm
import alert_app.routes.routes_competitors as rc


def _request():
    return types.SimpleNamespace(url=types.SimpleNamespace(path="/"), method="POST")

def _monitored_payload():
    return types.SimpleNamespace(product_url="u", name_identification="n", target_price=1)

def _competitor_payload(monitored_id="m"):
    return types.SimpleNamespace(product_url="u", monitored_product_id=monitored_id)

def test_monitored_product_url_validation(monkeypatch):
    monkeypatch.setattr(rm, "is_product_url", lambda url: False)
    monkeypatch.setattr(rm, "canonicalize_ml_url", lambda url: "should-not-call")
    with pytest.raises(HTTPException) as exc:
        rm.create_scrape_product(_request(), _monitored_payload(), db=None, user=types.SimpleNamespace(id="u"))
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

def test_competitor_product_url_validation(monkeypatch):
    monkeypatch.setattr(rc, "is_product_url", lambda url: False)
    monkeypatch.setattr(rc, "canonicalize_ml_url", lambda url: "should-not-call")
    with pytest.raises(HTTPException) as exc:
        rc.create_competitor_scrape(_request(), _competitor_payload(), db=None, user=types.SimpleNamespace(id="u"))
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
