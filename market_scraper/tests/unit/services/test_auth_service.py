import uuid
from types import SimpleNamespace
import pytest
from fastapi import HTTPException

from alert_app.services import services_auth as auth


class DummyDB:
    def __init__(self):
        self.commited = False

    def commit(self):
        self.commited = True

class DummyUser:
    def __init__(self, active=True):
        self.id = uuid.uuid4()
        self.is_active = active
        self.last_login = None
        self.password_checked = None

    def check_password(self, pw):
        self.password_checked = pw
        return pw == "correct"

def test_authenticate_user_success(monkeypatch):
    user = DummyUser()
    db = DummyDB()
    monkeypatch.setattr(auth, "get_user_by_email", lambda db_, email: user)

    result = auth.authenticate_user(db, "e@example.com", "correct")

    assert result is user
    assert user.password_checked == "correct"

def test_authenticate_user_invalid(monkeypatch):
    user = DummyUser()
    db = DummyDB()
    monkeypatch.setattr(auth, "get_user_by_email", lambda db_, email: user)

    result = auth.authenticate_user(db, "e@example.com", "wrong")

    assert result is None
    assert user.password_checked == "wrong"

# ---------- Login User ----------

def _make_request():
    return SimpleNamespace(client=SimpleNamespace(host="1.1.1.1"), headers={})

def test_login_user_success(monkeypatch):
    user = DummyUser(active=True)
    db = DummyDB()
    monkeypatch.setattr(auth, "block_ip", lambda req: None)
    monkeypatch.setattr(auth, "authenticate_user", lambda db_, e, p: user)
    called = {}
    monkeypatch.setattr(auth, "reset_failed_attempts", lambda req: called.setdefault("reset", True))
    monkeypatch.setattr(auth, "create_access_token", lambda payload: "token")

    result = auth.login_user(_make_request(), db, "e@example.com", "correct")

    assert db.commited
    assert called.get("reset")
    assert user.last_login is not None
    assert result.access_token == "token"

def test_login_user_wrong_password(monkeypatch):
    db = DummyDB()
    monkeypatch.setattr(auth, "block_ip", lambda req: None)
    monkeypatch.setattr(auth, "authenticate_user", lambda *a: None)
    called = {}
    monkeypatch.setattr(auth, "record_failed_attempt", lambda req: called.setdefault("fail", True))

    with pytest.raises(HTTPException) as exc:
        auth.login_user(_make_request(), db, "e@example.com", "bad")

    assert exc.value.status_code == 401
    assert called.get("fail")
    assert not db.commited

def test_login_user_inactive(monkeypatch):
    user = DummyUser(active=False)
    db = DummyDB()
    monkeypatch.setattr(auth, "block_ip", lambda req: None)
    monkeypatch.setattr(auth, "authenticate_user", lambda *a: user)
    called = {}
    monkeypatch.setattr(auth, "record_failed_attempt", lambda req: called.setdefault("fail", True))

    with pytest.raises(HTTPException) as exc:
        auth.login_user(_make_request(), db, "e@example.com", "correct")

    assert exc.value.status_code == 403
    assert called.get("fail")
    assert not db.commited

# ---------- Refresh Token ----------

class DummyRefresh:
    def __init__(self, user_id):
        self.id = uuid.uuid4()
        self.user_id = user_id
        self.revoked = False

def test_refresh_token_success(monkeypatch):
    db = DummyDB()
    refresh = DummyRefresh(uuid.uuid4())
    monkeypatch.setattr(auth, "get_refresh_token", lambda db_, raw: refresh)
    monkeypatch.setattr(auth, "revoke_refresh_token", lambda db_, ref: setattr(ref, "revoked", True))
    monkeypatch.setattr(auth, "create_refresh_token", lambda db_, uid, ip, ua: ("new", DummyRefresh(uuid.UUID(uid))))
    monkeypatch.setattr(auth, "create_access_token", lambda payload: "access")

    payload = SimpleNamespace(refresh_token="old")
    req = _make_request()
    result = auth.refresh_token_service(db, payload, req)

    assert refresh.revoked
    assert result.access_token == "access"
    assert result.refresh_token == "new"
    assert db.commited is False

def test_refresh_token_invalid(monkeypatch):
    db = DummyDB()
    monkeypatch.setattr(auth, "get_refresh_token", lambda db_, raw: None)

    with pytest.raises(HTTPException) as exc:
        auth.refresh_token_service(db, SimpleNamespace(refresh_token="x"), _make_request())

    assert exc.value.status_code == 401
