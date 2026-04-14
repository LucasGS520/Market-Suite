""" Testes unitarios para verificacao e reenvio de identidade. """

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from market_alert.enums.enums_users import UserStatus
from market_alert.users.services import services_identity


pytestmark = pytest.mark.unit


def test_verify_email_activates_pending_user_when_phone_is_not_required(monkeypatch) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        status=UserStatus.pending,
        phone_number=None,
        phone_number_verified=False,
    )
    status_changes: list[tuple[object, object]] = []
    email_verifications: list[object] = []

    monkeypatch.setattr(
        services_identity.crud_identity,
        "consume_verification",
        lambda db, kind, raw_token: SimpleNamespace(user_id=user_id),
    )
    monkeypatch.setattr(
        services_identity.crud_account,
        "get_user_by_id",
        lambda db, returned_user_id: user,
    )
    monkeypatch.setattr(
        services_identity.crud_account,
        "set_email_verified",
        lambda db, current_user: email_verifications.append(current_user),
    )
    monkeypatch.setattr(
        services_identity.crud_account,
        "set_status",
        lambda db, current_user, target_status: status_changes.append((current_user, target_status)),
    )

    result = services_identity.verify_email(object(), "token-1")

    assert result is user
    assert email_verifications == [user]
    assert status_changes == [(user, UserStatus.active)]


def test_verify_phone_otp_rejects_user_without_phone(monkeypatch) -> None:
    user = SimpleNamespace(phone_number=None)

    monkeypatch.setattr(services_identity.crud_account, "get_user_by_id", lambda db, user_id: user)

    with pytest.raises(HTTPException) as exc_info:
        services_identity.verify_phone_otp(object(), uuid4(), "123456")

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_verify_phone_otp_marks_phone_and_activates_pending_user(monkeypatch) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        phone_number="+5511998761234",
        email_verified=True,
        status=UserStatus.pending,
    )
    verification = SimpleNamespace(attempts_remaining=3)
    phone_verified: list[object] = []
    status_changes: list[tuple[object, object]] = []

    monkeypatch.setattr(services_identity.crud_account, "get_user_by_id", lambda db, current_id: user)
    monkeypatch.setattr(
        services_identity.crud_identity,
        "get_active_by_user",
        lambda db, current_id, kind: verification,
    )
    monkeypatch.setattr(services_identity, "enforce_rate_limit", lambda **kwargs: None)
    monkeypatch.setattr(
        services_identity.crud_identity,
        "consume_verification",
        lambda db, kind, raw_token, user_id=None: verification,
    )
    monkeypatch.setattr(
        services_identity.crud_account,
        "set_phone_verified",
        lambda db, current_user: phone_verified.append(current_user),
    )
    monkeypatch.setattr(
        services_identity.crud_account,
        "set_status",
        lambda db, current_user, target_status: status_changes.append((current_user, target_status)),
    )

    result = services_identity.verify_phone_otp(object(), user_id, "123456")

    assert result is user
    assert phone_verified == [user]
    assert status_changes == [(user, UserStatus.active)]


def test_resend_verification_rejects_invalid_channel(monkeypatch, build_request) -> None:
    user = SimpleNamespace(id=uuid4(), phone_number="+5511998761234")

    monkeypatch.setattr(services_identity, "enforce_rate_limit", lambda **kwargs: None)
    monkeypatch.setattr(services_identity, "resolve_client_ip", lambda request: "198.51.100.20")

    payload = SimpleNamespace(channel="invalid")

    with pytest.raises(HTTPException) as exc_info:
        services_identity.resend_verification(object(), user, payload, build_request())

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
