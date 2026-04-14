from __future__ import annotations

import pytest


@pytest.fixture
def auth_user_payload(build_user_payload):
    return build_user_payload()


@pytest.fixture
def login_payload(auth_user_payload):
    return {
        "email": auth_user_payload["email"],
        "password": auth_user_payload["password"],
    }


@pytest.fixture
def refresh_payload():
    return {"refresh_token": "refresh-token-for-tests"}


@pytest.fixture
def auth_request(build_request):
    return build_request(
        headers={
            "user-agent": "pytest-agent",
            "x-real-ip": "203.0.113.10",
            "x-request-id": "req-auth-1",
        }
    )
