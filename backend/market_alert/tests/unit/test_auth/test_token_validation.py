""" Testes unitarios para login, refresh e resolucao de tokens. """

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from market_alert.auth.services import services_auth
from market_alert.enums.enums_users import UserStatus
from market_alert.schemas.schemas_auth import RefreshRequest


pytestmark = pytest.mark.unit


class _FakeSession:
    def __init__(self) -> None:
        self.commit_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1


def test_resolve_refresh_token_prefers_cookie_over_payload(auth_request) -> None:
    request = auth_request
    request._cookies = {
        services_auth.settings.REFRESH_TOKEN_COOKIE_NAME: "cookie-refresh"
    }

    resolved = services_auth._resolve_refresh_token(
        RefreshRequest(refresh_token="payload-refresh"),
        request,
    )

    assert resolved == "cookie-refresh"


def test_authenticate_user_falls_back_to_phone_when_email_lookup_fails(monkeypatch) -> None:
    user = SimpleNamespace(check_password=lambda value: value == "Secure123")

    monkeypatch.setattr(services_auth, "get_user_by_email", lambda db, identifier: None)
    monkeypatch.setattr(services_auth, "get_user_by_phone", lambda db, identifier: user)

    authenticated = services_auth.authenticate_user(object(), "+5511999999999", "Secure123")

    assert authenticated is user


def test_login_user_resets_failures_and_returns_token_pair(monkeypatch, auth_request) -> None:
    db = _FakeSession()
    user = SimpleNamespace(
        id=uuid4(),
        email_verified=True,
        phone_number_verified=False,
        role="user",
        status=UserStatus.active,
        is_active=True,
        last_login=None,
    )
    reset_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(services_auth, "resolve_client_ip", lambda request: "203.0.113.10")
    monkeypatch.setattr(services_auth, "compute_device_fingerprint", lambda ip, agent: "fp-1")
    monkeypatch.setattr(services_auth, "block_ip", lambda request, identifier="", fingerprint="": None)
    monkeypatch.setattr(services_auth, "authenticate_user", lambda db, username, password: user)
    monkeypatch.setattr(
        services_auth,
        "reset_failed_attempts",
        lambda request, identifier="", fingerprint="": reset_calls.append((identifier, fingerprint)),
    )
    monkeypatch.setattr(services_auth, "create_access_token", lambda payload: "access-token")
    monkeypatch.setattr(
        services_auth,
        "create_refresh_token",
        lambda db, user_id, ip, user_agent: ("refresh-token", SimpleNamespace(id=uuid4())),
    )

    result = services_auth.login_user(auth_request, db, "user@example.com", "Secure123")

    assert result.access_token == "access-token"
    assert result.refresh_token == "refresh-token"
    assert db.commit_calls == 1
    assert user.last_login is not None
    assert reset_calls == [("user@example.com", "fp-1")]


def test_login_user_rejects_inactive_user_and_records_failure(monkeypatch, auth_request) -> None:
    db = _FakeSession()
    inactive_user = SimpleNamespace(
        id=uuid4(),
        is_active=False,
        status=UserStatus.active,
    )
    recorded: list[tuple[str, str]] = []

    monkeypatch.setattr(services_auth, "resolve_client_ip", lambda request: "203.0.113.10")
    monkeypatch.setattr(services_auth, "compute_device_fingerprint", lambda ip, agent: "fp-1")
    monkeypatch.setattr(services_auth, "block_ip", lambda request, identifier="", fingerprint="": None)
    monkeypatch.setattr(services_auth, "authenticate_user", lambda db, username, password: inactive_user)
    monkeypatch.setattr(
        services_auth,
        "record_failed_attempt",
        lambda request, identifier="", fingerprint="": recorded.append((identifier, fingerprint)),
    )

    with pytest.raises(HTTPException) as exc_info:
        services_auth.login_user(auth_request, db, "user@example.com", "Secure123")

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert recorded == [("user@example.com", "fp-1")]


def test_refresh_token_service_rotates_tokens_when_refresh_is_valid(monkeypatch, auth_request) -> None:
    db = object()
    refresh = SimpleNamespace(id=uuid4(), user_id=uuid4())
    user = SimpleNamespace(
        email_verified=True,
        phone_number_verified=True,
        role="user",
        status=UserStatus.active,
    )
    rate_limit_keys: list[str] = []
    revoked: list[object] = []

    monkeypatch.setattr(services_auth, "resolve_client_ip", lambda request: "203.0.113.10")
    monkeypatch.setattr(services_auth, "compute_device_fingerprint", lambda ip, agent: "fp-1")
    monkeypatch.setattr(services_auth, "_resolve_refresh_token", lambda payload, request: "raw-refresh")
    monkeypatch.setattr(services_auth, "get_refresh_token", lambda db, raw_token: refresh)
    monkeypatch.setattr(
        services_auth,
        "enforce_rate_limit",
        lambda **kwargs: rate_limit_keys.append(kwargs["key"]),
    )
    monkeypatch.setattr(services_auth, "revoke_refresh_token", lambda db, token: revoked.append(token))
    monkeypatch.setattr(
        services_auth,
        "create_refresh_token",
        lambda db, user_id, ip, user_agent: ("new-refresh", SimpleNamespace(id=uuid4())),
    )
    monkeypatch.setattr(services_auth, "get_user_by_id", lambda db, user_id: user)
    monkeypatch.setattr(services_auth, "create_access_token", lambda payload: "new-access")

    result = services_auth.refresh_token_service(db, RefreshRequest(), auth_request)

    assert result.access_token == "new-access"
    assert result.refresh_token == "new-refresh"
    assert revoked == [refresh]
    assert rate_limit_keys == [
        f"rate:auth:refresh:{refresh.user_id}",
        "rate:auth:device-refresh:fp-1",
    ]


def test_refresh_token_service_rejects_missing_refresh_token(monkeypatch, auth_request) -> None:
    monkeypatch.setattr(services_auth, "_resolve_refresh_token", lambda payload, request: None)
    monkeypatch.setattr(services_auth, "resolve_client_ip", lambda request: "203.0.113.10")
    monkeypatch.setattr(services_auth, "compute_device_fingerprint", lambda ip, agent: "fp-1")

    with pytest.raises(HTTPException) as exc_info:
        services_auth.refresh_token_service(object(), None, auth_request)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
