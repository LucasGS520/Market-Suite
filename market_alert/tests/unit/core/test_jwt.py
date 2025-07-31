from datetime import timedelta
import pytest
from fastapi import HTTPException
from app.core.jwt import create_access_token, verify_access_token

def test_create_and_verify_token():
    token = create_access_token({"sub": "user1"})
    payload = verify_access_token(token)
    assert payload["sub"] == "user1"


def test_expired_token(monkeypatch):
    token = create_access_token({"sub": "u"}, expires_delta=timedelta(seconds=-1))
    with pytest.raises(HTTPException):
        verify_access_token(token)

def test_invalid_token():
    with pytest.raises(HTTPException):
        verify_access_token("invalid")
