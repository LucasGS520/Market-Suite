import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from alert_app.routes.auth import routes_login as r_login
from alert_app.routes.auth import routes_logout as r_logout
from alert_app.routes.auth import routes_refresh as r_refresh
from alert_app.routes.auth import routes_verify as r_verify
from alert_app.routes.auth import routes_reset_password as r_reset


class DummyCounter:
    def __init__(self):
        self.count = 0

    def labels(self, **k):
        return self

    def inc(self):
        self.count += 1

def _request():
    return SimpleNamespace(client=SimpleNamespace(host="1.1.1.1"), headers={})

def test_login_invalid_credentials_increments_metric(monkeypatch):
    counter = DummyCounter()
    monkeypatch.setattr(r_login.metrics, "LOGIN_ERRORS_TOTAL", counter)

    def fake_login(req, db, u, p):
        raise HTTPException(status_code=401)

    monkeypatch.setattr(r_login, "login_user", fake_login)

    with pytest.raises(HTTPException) as exc:
        r_login.login(_request(), form_data=SimpleNamespace(username="e", password="p"), db=None)

    assert exc.value.status_code == 401
    assert counter.count == 1

def test_logout_propagates_error(monkeypatch):
    def fake_logout(db, payload, request):
        raise HTTPException(status_code=404)

    monkeypatch.setattr(r_logout, "logout_service", fake_logout)

    with pytest.raises(HTTPException) as exc:
        r_logout.logout(SimpleNamespace(refresh_token="t"), _request(), db=None)

    assert exc.value.status_code == 404

def test_refresh_propagates_error(monkeypatch):
    def fake_refresh(db, payload, request):
        raise HTTPException(status_code=401)

    monkeypatch.setattr(r_refresh, "refresh_token_service", fake_refresh)

    with pytest.raises(HTTPException) as exc:
        r_refresh.refresh_tokens(SimpleNamespace(refresh_token="t"), _request(), db=None)

    assert exc.value.status_code == 401

def test_verify_confirm_propagates_error(monkeypatch):
    def fake_confirm(db, payload):
        raise HTTPException(status_code=400)

    monkeypatch.setattr(r_verify, "confirm_email_verification_service", fake_confirm)

    with pytest.raises(HTTPException) as exc:
        r_verify.confirm_verification(SimpleNamespace(token="x"), db=None)

    assert exc.value.status_code == 400

def test_reset_confirm_propagates_erro(monkeypatch):
    def fake_confirm(db, payload):
        raise HTTPException(status_code=400)

    monkeypatch.setattr(r_reset,"confirm_password_service", fake_confirm)

    with pytest.raises(HTTPException) as exc:
        r_reset.confirm_reset_password(SimpleNamespace(token="x", new_password="n"), db=None)

    assert exc.value.status_code == 400
