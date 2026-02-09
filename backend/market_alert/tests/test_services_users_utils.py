""" Testes das normalizações de dados de usuário """

from __future__ import annotations

import pytest
from fastapi import HTTPException

from market_alert.services.services_users import _normalize_email, _normalize_phone


def test_normalize_email_lowercase() -> None:
    """ Normaliza emails removendo espaços e aplicando lower-case """
    assert _normalize_email("  Usuario@Exemplo.COM ") == "usuario@exemplo.com"


def test_normalize_phone_valido() -> None:
    """ Aceita telefone válido e retorna formato E.164 """
    telefone = _normalize_phone("+55 11 99999-9999")

    assert telefone == "+5511999999999"


def test_normalize_phone_invalido() -> None:
    """ Rejeita telefone inválido com erro HTTP 422 """
    with pytest.raises(HTTPException) as excinfo:
        _normalize_phone("123")

    assert excinfo.value.status_code == 422
    