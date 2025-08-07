import uuid
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from datetime import datetime, timezone, timedelta

from alert_app.core import security
from alert_app.core import tokens


class DummyDB:
    def __init__(self, user=None):
        self.user = user

    def get(self, models, pk):
        return self.user

class DummyUser:
    def __init__(self, role="user", active=True):
        self.id = uuid.uuid4()
        self.role = role
        self.is_active = active

@pytest.mark.asyncio
async def test_get_current_user_success(monkeypatch):
    user = DummyUser()
    db = DummyDB(user)
    monkeypatch.setattr(security, "verify_access_token", lambda tok: {"sub": str(user.id)})
    creds = SimpleNamespace(credentials="tok")
    result = await security.get_current_user(creds, db)
    assert result is user

@pytest.mark.asyncio
async def test_get_current_user_not_found(monkeypatch):
    db = DummyDB(None)
    monkeypatch.setattr(security, "verify_access_token", lambda tok: {"sub": str(uuid.uuid4())})
    with pytest.raises(HTTPException) as exc:
        await security.get_current_user(SimpleNamespace(credentials="t"), db)
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_get_current_user_inactive(monkeypatch):
    user = DummyUser(active=False)
    db = DummyDB(user)
    monkeypatch.setattr(security, "verify_access_token", lambda tok: {"sub": str(user.id)})
    with pytest.raises(HTTPException) as exc:
        await security.get_current_user(SimpleNamespace(credentials="t"), db)
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_get_current_user_bad_sub(monkeypatch):
    db = DummyDB(None)
    monkeypatch.setattr(security, "verify_access_token", lambda tok: {"sub": "not-a-uuid"})
    with pytest.raises(HTTPException) as exc:
        await security.get_current_user(SimpleNamespace(credentials="t"), db)
    assert exc.value.status_code == 401

@pytest.mark.asyncio
async def test_get_current_admin_user(monkeypatch):
    user = DummyUser(role="admin")
    db = DummyDB(user)
    monkeypatch.setattr(security, "verify_access_token", lambda tok: {"sub": str(user.id)})
    creds = SimpleNamespace(credentials="tok")
    current = await security.get_current_user(creds, db)
    result = security.get_current_admin_user(current)
    assert result is user

@pytest.mark.asyncio
async def test_get_current_admin_user_denied(monkeypatch):
    user = DummyUser(role="user")
    db = DummyDB(user)
    monkeypatch.setattr(security, "verify_access_token", lambda tok: {"sub": str(user.id)})
    creds = SimpleNamespace(credentials="tok")
    current = await security.get_current_user(creds, db)
    with pytest.raises(HTTPException) as exc:
        security.get_current_admin_user(current)
    assert exc.value.status_code == 403

def test_verification_token_unique():
    a = tokens.generate_verification_token()
    b = tokens.generate_verification_token()
    assert a != b and isinstance(a, str) and isinstance(b, str)

def test_reset_token_unique():
    a = tokens.generate_reset_token()
    b = tokens.generate_reset_token()
    assert a != b and isinstance(a, str) and isinstance(b, str)

def test_token_expiry(monkeypatch):
    fixed = datetime(2020, 1, 1, tzinfo=timezone.utc)
    class FixedDatetime:
        @classmethod
        def now(cls, tz=None):
            return fixed
    monkeypatch.setattr(tokens, "datetime", FixedDatetime)
    exp = tokens.token_expiry(30)
    assert exp == fixed + timedelta(minutes=30)
