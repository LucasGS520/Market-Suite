""" Testes unitarios para validacao de senha e contratos de auth. """

import pytest
from pydantic import ValidationError

from market_alert.schemas.schemas_auth import (
    ChangePasswordRequest,
    ResetPasswordConfirmRequest,
    password_validator,
)


pytestmark = pytest.mark.unit


def test_password_validator_accepts_alphanumeric_password() -> None:
    assert password_validator("StrongPass123") == "StrongPass123"


def test_password_validator_rejects_short_password() -> None:
    with pytest.raises(ValueError, match="ao menos 8 caracteres"):
        password_validator("Abc123")


def test_password_validator_rejects_password_without_digits() -> None:
    with pytest.raises(ValueError, match="letras e n"):
        password_validator("StrongPass")


def test_reset_password_confirm_request_validates_password_strength() -> None:
    request = ResetPasswordConfirmRequest(
        token="token-123456",
        new_password="Secure123",
    )

    assert request.new_password == "Secure123"


def test_change_password_request_rejects_weak_password() -> None:
    with pytest.raises(ValidationError, match="letras e n"):
        ChangePasswordRequest(old_password="Old12345", new_password="weakpass")
