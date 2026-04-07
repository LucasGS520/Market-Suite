from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shared.infra.db import get_db

from market_alert.infrastructure.security.auth_context import get_current_user


HIGH_COST_INTEGRATION = pytest.mark.integration_high_cost


@pytest.fixture
def integration_user_payload(build_user_payload):
    return build_user_payload()


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-access-token"}


@pytest.fixture
def mark_high_cost_integration() -> pytest.MarkDecorator:
    return HIGH_COST_INTEGRATION


@pytest.fixture
def integration_now() -> datetime:
    return datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def integration_state() -> dict[str, Any]:
    return {
        "users": {},
        "refresh_tokens": set(),
        "monitored": {},
        "comparisons": {},
        "notifications": [],
        "preferences": [],
        "events": [],
    }


@pytest.fixture
def integration_db_session() -> SimpleNamespace:
    return SimpleNamespace(name="integration-db-session")


@pytest.fixture
def integration_current_user(integration_user_payload) -> SimpleNamespace:
    return SimpleNamespace(**integration_user_payload)


@pytest.fixture
def app_factory(monkeypatch, integration_db_session, integration_current_user):
    import market_alert.main as main_app

    def _build() -> Any:
        monkeypatch.setattr(main_app, "validate_startup_dependencies", lambda strict=True: True)
        app = main_app.create_app()
        # Mantemos a suíte determinística sem bootstrap real de infra.
        app.router.on_startup = []
        app.dependency_overrides[get_db] = lambda: integration_db_session
        app.dependency_overrides[get_current_user] = lambda: integration_current_user
        return app

    return _build


@pytest.fixture
def api_client(app_factory):
    app = app_factory()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
