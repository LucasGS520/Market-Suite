""" Testes unitarios para normalizacao e regras basicas de usuarios. """

from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from market_alert.schemas.schemas_users import UserCreate, UserUpdate
from market_alert.users.domain import account_domain
from market_alert.users.services import services_account


pytestmark = pytest.mark.unit


class _TaskRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def delay(self, *args) -> None:
        self.calls.append(args)


def test_normalize_email_trims_and_lowercases() -> None:
    assert account_domain.normalize_email("  User@Example.COM  ") == "user@example.com"


def test_normalize_phone_returns_e164_format() -> None:
    normalized = account_domain.normalize_phone("(11) 99876-1234")

    assert normalized == "+5511998761234"


def test_normalize_phone_rejects_invalid_number() -> None:
    with pytest.raises(HTTPException) as exc_info:
        account_domain.normalize_phone("123")

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_update_user_requires_at_least_one_field(monkeypatch) -> None:
    monkeypatch.setattr(services_account.crud_account, "update_user", lambda db, user_id, updates: None)

    with pytest.raises(HTTPException) as exc_info:
        services_account.update_user(object(), uuid4(), UserUpdate())

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_register_user_normalizes_identifiers_and_creates_verifications(
    monkeypatch,
    build_request,
) -> None:
    email_task = _TaskRecorder()
    phone_task = _TaskRecorder()
    created_verifications: list[dict[str, object]] = []
    created_payloads: list[UserCreate] = []
    user = SimpleNamespace(id=uuid4())
    fake_tasks_module = SimpleNamespace(
        send_email_verification=email_task,
        send_phone_otp=phone_task,
    )

    monkeypatch.setitem(sys.modules, "market_alert.users.tasks.verification_tasks", fake_tasks_module)
    monkeypatch.setattr(services_account, "enforce_rate_limit", lambda **kwargs: None)
    monkeypatch.setattr(services_account, "resolve_client_ip", lambda request: "198.51.100.20")
    monkeypatch.setattr(
        services_account.crud_account,
        "create_user",
        lambda db, payload: created_payloads.append(payload) or user,
    )
    monkeypatch.setattr(
        services_account.crud_identity,
        "create_verification",
        lambda db, **kwargs: created_verifications.append(kwargs),
    )
    monkeypatch.setattr(services_account, "generate_verification_token", lambda: "email-token")
    monkeypatch.setattr(services_account, "generate_phone_otp", lambda: "123456")
    monkeypatch.setattr(
        services_account,
        "token_expiry",
        lambda minutes: datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    payload = UserCreate(
        name="User Test",
        email="  User@Example.COM ",
        phone_number="+5511998761234",
        password="StrongPass123",
    )
    request = build_request(headers={"user-agent": "pytest-users"})

    result = services_account.register_user(object(), payload, request)

    assert result is user
    assert created_payloads[0].email == "user@example.com"
    assert created_payloads[0].phone_number == "+5511998761234"
    assert len(created_verifications) == 2
    assert email_task.calls == [(str(user.id), "email-token")]
    assert phone_task.calls == [(str(user.id), "123456")]
