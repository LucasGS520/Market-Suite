""" Testes de validação dos esquemas relacionados a usuários """

import pytest
from pydantic import ValidationError

from market_alert.schemas.schemas_users import UserCreate


def test_user_create_rejects_password_without_numbers():
    """Garante que senhas sem números sejam recusadas na criação"""

    with pytest.raises(ValidationError, match="A senha deve conter letras e números"):
        UserCreate(
            name="Usuário Teste",
            email="teste@example.com",
            phone_number="11999999999",
            password="somenteletras",
        )


def test_user_create_rejects_password_without_letters():
    """Garante que senhas sem letras sejam recusadas na criação"""

    with pytest.raises(ValidationError, match="A senha deve conter letras e números"):
        UserCreate(
            name="Usuário Teste",
            email="teste@example.com",
            phone_number="11999999999",
            password="1234567890",
        )
        