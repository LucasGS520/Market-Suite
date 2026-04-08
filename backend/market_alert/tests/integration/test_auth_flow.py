""" Testes de integração controlada para cadastro, login, refresh e logout. """

from __future__ import annotations

from types import SimpleNamespace

import pytest

from market_alert.auth.routes_auth import routes_login, routes_logout, routes_refresh
from market_alert.users.routes import routes_account


pytestmark = pytest.mark.integration


def test_auth_register_login_refresh_logout_flow(
    monkeypatch,
    api_client,
    integration_state,
    user_payload,
) -> None:
    password = user_payload["password"]
    request_name = "Test User"

    def _register_user(db, user_data, request):
        persisted = dict(user_payload)
        persisted["email"] = user_data.email.strip().lower()
        integration_state["users"][persisted["email"]] = persisted
        return SimpleNamespace(**persisted)

    def _login_user(request, db, username, password_value):
        assert username in integration_state["users"]
        assert password_value == password
        integration_state["refresh_tokens"].add("refresh-token-1")
        return SimpleNamespace(
            access_token="access-token-1",
            refresh_token="refresh-token-1",
            token_type="bearer",
        )

    def _refresh_token_service(db, payload, request):
        current_refresh = request.cookies.get("refresh_token") or (payload.refresh_token if payload else None)
        assert current_refresh == "refresh-token-1"
        integration_state["refresh_tokens"].discard(current_refresh)
        integration_state["refresh_tokens"].add("refresh-token-2")
        return SimpleNamespace(
            access_token="access-token-2",
            refresh_token="refresh-token-2",
            token_type="bearer",
        )

    def _logout_service(db, payload, request):
        current_refresh = request.cookies.get("refresh_token") or (payload.refresh_token if payload else None)
        integration_state["refresh_tokens"].discard(current_refresh)

    monkeypatch.setattr(routes_account, "validate_phone_number", lambda phone_number: None)
    monkeypatch.setattr(routes_account, "register_user", _register_user)
    monkeypatch.setattr(routes_login, "login_user", _login_user)
    monkeypatch.setattr(routes_refresh, "refresh_token_service", _refresh_token_service)
    monkeypatch.setattr(routes_logout, "logout_service", _logout_service)

    register_response = api_client.post(
        "/users/",
        json={
            "name": request_name,
            "email": user_payload["email"],
            "phone_number": user_payload["phone_number"],
            "password": password,
        },
    )
    assert register_response.status_code == 200
    assert register_response.json()["email"] == user_payload["email"].strip().lower()

    login_response = api_client.post(
        "/auth/login",
        data={"username": user_payload["email"], "password": password},
    )
    assert login_response.status_code == 200
    assert login_response.json()["access_token"] == "access-token-1"
    assert "refresh_token=" in login_response.headers["set-cookie"]
    assert "refresh-token-1" in integration_state["refresh_tokens"]

    refresh_response = api_client.post("/auth/refresh")
    assert refresh_response.status_code == 200
    assert refresh_response.json()["access_token"] == "access-token-2"
    assert "refresh-token-1" not in integration_state["refresh_tokens"]
    assert "refresh-token-2" in integration_state["refresh_tokens"]

    logout_response = api_client.post("/auth/logout")
    assert logout_response.status_code == 204
    assert "refresh-token-2" not in integration_state["refresh_tokens"]
    assert "refresh_token=" in logout_response.headers["set-cookie"]
