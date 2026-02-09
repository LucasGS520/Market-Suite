""" Testes essenciais de autenticação, tokens e senha """

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException

from market_alert.core.jwt import create_access_token, verify_access_token
from market_alert.core.password import hash_password, verify_password
from market_alert.core.tokens import (
    generate_phone_otp,
    generate_reset_token,
    generate_verification_token,
    hash_token,
    token_expiry,
)


def test_hash_password_e_verificacao() -> None:
    """ Confirma que o hashing de senha é validado corretamente """
    senha = "SenhaSegura123"
    hashed = hash_password(senha)

    assert verify_password(senha, hashed) is True
    assert verify_password("errada", hashed) is False


def test_tokens_basicos_e_hash() -> None:
    """  tokens e verifica hash determinístico """
    verification = generate_verification_token()
    reset = generate_reset_token()
    otp = generate_phone_otp()

    assert verification != reset
    assert otp.isdigit() and len(otp) == 6

    hashed_once = hash_token("token_bruto")
    hashed_twice = hash_token("token_bruto")

    assert hashed_once == hashed_twice


def test_token_expiry_retorna_future() -> None:
    """ Verifica que a expiração retorna data futura em UTC """
    expire_at = token_expiry(minutes=5)

    assert expire_at.tzinfo is not None


def test_jwt_criacao_e_validacao() -> None:
    """ Gera e valida um JWT simples """
    token = create_access_token({"sub": "usuario"}, expires_delta=timedelta(minutes=5))
    payload = verify_access_token(token)

    assert payload["sub"] == "usuario"


def test_jwt_expirado_gera_erro() -> None:
    """ Confirma que tokens expirados retornam HTTP 401 """
    token = create_access_token({"sub": "usuario"}, expires_delta=timedelta(minutes=-1))

    with pytest.raises(HTTPException) as excinfo:
        verify_access_token(token)

    assert excinfo.value.status_code == 401
    