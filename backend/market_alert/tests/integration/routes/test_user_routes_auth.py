""" Testes de autorização para rotas de gerenciamento de usuários. """

from uuid import uuid4

from fastapi import status


def _build_user_payload():
    """Monta um payload válido e único para criação de usuário."""
    unique = uuid4().hex
    unique_letters = "".join(ch for ch in unique if ch.isalpha())[:6]
    return {
        "name": f"Usuario {unique_letters or 'Teste'}",
        "email": f"novo_{unique}@exemplo.com",
        "password": "Senha1234",
        "phone_number": "11999998888",
        "notifications_enabled": True,
    }


def test_create_user_requires_authentication(unauthenticated_client, prepare_test_database):
    """Garante que chamadas sem token sejam bloqueadas pelo esquema HTTPBearer."""
    payload = _build_user_payload()
    response = unauthenticated_client.post("/users/", json=payload)

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_non_admin_cannot_create_user(client, prepare_test_database):
    """Verifica que usuários autenticados sem papel de admin recebem erro 403."""
    payload = _build_user_payload()
    response = client.post("/users/", json=payload)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Permissão negada: apenas administradores"


def test_admin_can_manage_user_status(admin_client, prepare_test_database):
    """Confirma que administradores conseguem criar usuários e alterar status."""
    payload = _build_user_payload()
    creation_response = admin_client.post("/users/", json=payload)

    assert creation_response.status_code == status.HTTP_200_OK
    created_user = creation_response.json()

    status_response = admin_client.put(
        f"/users/{created_user['id']}/status",
        params={"active": False},
    )

    assert status_response.status_code == status.HTTP_200_OK
    assert status_response.json()["is_active"] is False
    