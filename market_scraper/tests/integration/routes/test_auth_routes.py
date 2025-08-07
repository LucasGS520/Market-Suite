from fastapi import HTTPException

from alert_app.routes.auth import routes_login as r_login
from alert_app.routes.auth import routes_refresh as r_refresh
from alert_app.routes.auth import routes_logout as r_logout
from alert_app.routes.auth import routes_profile as r_profile
from alert_app.routes.auth import routes_verify as r_verify
from alert_app.routes.auth import routes_reset_password as r_reset


class Dummy:
    def __init__(self):
        self.called = False
        self.payload = None

    def __call__(self, *a, **k):
        self.called = True
        self.payload = (a, k)
        return {"msg": "ok"}

def test_login_success(client, monkeypatch, prepare_test_database):
    monkeypatch.setattr(r_login, "login_user", lambda req, db, u, p: {"access_token": "tok", "token_type": "bearer"})
    resp = client.post("/auth/", data={"username": "e", "password": "p"})
    assert resp.status_code == 200
    assert resp.json()["access_token"] == "tok"

def test_login_failure(client, monkeypatch, prepare_test_database):
    def fail(req, db, u, p):
        raise HTTPException(status_code=401)
    monkeypatch.setattr(r_login, "login_user", fail)
    resp = client.post("/auth/", data={"username": "e", "password": "bad"})
    assert resp.status_code == 401

def test_refresh_and_logout(client, monkeypatch, prepare_test_database):
    monkeypatch.setattr(r_refresh, "refresh_token_service", lambda db, p, r: {"access_token": "a", "refresh_token": "b", "token_type": "bearer"})
    resp = client.post("/auth/refresh", json={"refresh_token": "x"})
    assert resp.status_code == 200
    monkeypatch.setattr(r_logout, "logout_service", lambda db, p, r: None)
    resp = client.post("/auth/logout", json={"refresh_token": "b"})
    assert resp.status_code == 204

def test_profile_endpoints(client, monkeypatch, prepare_test_database):
    cp = Dummy()
    ce = Dummy()
    monkeypatch.setattr(r_profile, "change_password_service", cp)
    monkeypatch.setattr(r_profile, "change_email_service", ce)
    resp = client.post("/auth/change-password", json={"old_password": "o", "new_password": "n1234567"})
    assert resp.status_code == 200
    resp = client.post("/auth/change-email", json={"new_email": "x@example.com"})
    assert resp.status_code == 200
    assert cp.called and ce.called

def test_email_verification_flow(client, monkeypatch, prepare_test_database):
    dm = Dummy()
    monkeypatch.setattr(r_verify, "send_verification_email_service", dm)
    resp = client.post("/auth/verify/request")
    assert resp.status_code == 200
    assert dm.called

    monkeypatch.setattr(r_verify, "confirm_email_verification_service", lambda db, p: None)
    resp = client.post("/auth/verify/confirm", json={"token": "123456"})
    assert resp.status_code == 200

def test_reset_password_flow(client, monkeypatch, prepare_test_database):
    monkeypatch.setattr(r_reset, "request_password_reset_service", lambda db, p: None)
    resp = client.post("/auth/reset_password/request", json={"email": "a@b.c"})
    assert resp.status_code == 200

    monkeypatch.setattr(r_reset, "confirm_password_service", lambda db, p: None)
    resp = client.post("/auth/reset_password/confirm", json={"token": "t", "new_password": "SenhaR3setada"})
    assert resp.status_code == 200
