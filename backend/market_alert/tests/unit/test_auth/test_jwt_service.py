""" Testes unitarios para emissao e validacao de JWT. """

from datetime import timedelta

import pytest
from fastapi import HTTPException, status

from market_alert.core.jwt import create_access_token, verify_access_token


pytestmark = pytest.mark.unit


def test_create_access_token_preserves_input_and_generates_exp_claim() -> None:
    payload = {"sub": "user-1", "roles": ["user"]}

    token = create_access_token(payload)
    decoded = verify_access_token(token)

    assert payload == {"sub": "user-1", "roles": ["user"]}
    assert decoded["sub"] == "user-1"
    assert decoded["roles"] == ["user"]
    assert "exp" in decoded


def test_verify_access_token_rejects_invalid_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        verify_access_token("invalid-token")

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail == "Token inválido"


def test_verify_access_token_rejects_expired_token() -> None:
    token = create_access_token({"sub": "user-1"}, expires_delta=timedelta(seconds=-1))

    with pytest.raises(HTTPException) as exc_info:
        verify_access_token(token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "Token expirado"
