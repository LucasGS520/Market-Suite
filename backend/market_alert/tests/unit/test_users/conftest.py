from __future__ import annotations

import pytest


@pytest.fixture
def user_create_payload(build_user_payload):
    payload = build_user_payload()
    return {
        "name": payload["name"],
        "email": payload["email"],
        "phone_number": payload["phone_number"],
        "password": payload["password"],
    }
