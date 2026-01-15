""" Testes do módulo services_auth """

import pytest
from types import SimpleNamespace
from fastapi import HTTPException

from market_alert.auth import services_auth


def test_authenticate_user_success(monkeypatch):
    dummy_user = SimpleNamespace(check_password=lambda pwd: pwd == "senha")
    monkeypatch.setattr(services_auth, "get_user_by_email", lambda db, email: dummy_user)
    assert services_auth.authenticate_user(None, "teste@example.com", "senha") is dummy_user

def test_authenticate_user_falha(monkeypatch):
    dummy_user = SimpleNamespace(check_password=lambda pwd: False)
    monkeypatch.setattr(services_auth, "get_user_by_email", lambda db, email: dummy_user)
    assert services_auth.authenticate_user(None, "teste@example.com", "senha") is None
    monkeypatch.setattr(services_auth, "get_user_by_email", lambda db, email: None)
    assert services_auth.authenticate_user(None, "test@example.com", "senha") is None

def test_change_email_service_success(monkeypatch):
    db = SimpleNamespace(commit=lambda: None)
    usuario = SimpleNamespace(id=1, email="antigo@example.com", email_verified=True, email_verified_at=None)
    monkeypatch.setattr(services_auth, "get_user_by_email", lambda db, email: None)
    req = SimpleNamespace(new_email="novo@example.com")
    services_auth.change_email_service(db, usuario, req)
    assert usuario.email == "novo@example.com"
    assert usuario.email_verified is False

def test_change_email_service_email_existente(monkeypatch):
    usuario = SimpleNamespace(id=1, email="antigo@example.com", email_verified=True, email_verified_at=None)
    monkeypatch.setattr(services_auth, "get_user_by_email", lambda db, email: object())
    req = SimpleNamespace(new_email="novo@example.com")
    with pytest.raises(HTTPException) as exc:
        services_auth.change_email_service(SimpleNamespace(), usuario, req)
    assert exc.value.status_code == 400

def test_refresh_token_service_success(monkeypatch):
    payload = SimpleNamespace(refresh_token="abc")
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={"user-agent": "teste"})
    refresh_obj = SimpleNamespace(user_id=123, id=1)
    monkeypatch.setattr(services_auth, "get_refresh_token", lambda db, token: refresh_obj)
    monkeypatch.setattr(services_auth, "revoke_refresh_token", lambda db, token: None)
    monkeypatch.setattr(services_auth, "create_refresh_token", lambda db, uid, host, agent: ("novo", SimpleNamespace(id=2, user_id=uid)))
    monkeypatch.setattr(services_auth, "create_access_token", lambda dados: "access")
    resp = services_auth.refresh_token_service(SimpleNamespace(), payload, request)
    assert resp.access_token == "access"
    assert resp.refresh_token == "novo"

def test_refresh_token_service_invalid(monkeypatch):
    payload = SimpleNamespace(refresh_token="invalido")
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})
    monkeypatch.setattr(services_auth, "get_refresh_token", lambda db, token: None)
    with pytest.raises(HTTPException) as exc:
        services_auth.refresh_token_service(SimpleNamespace(), payload, request)
    assert exc.value.status_code == 401
