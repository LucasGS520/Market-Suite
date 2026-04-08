from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from itertools import count
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4

import pytest
from fastapi import Request
from market_alert.comparisons.domain.price_competitiveness import ComparisonSnapshot

TESTS_DIR = Path(__file__).resolve().parent
MARKET_ALERT_DIR = TESTS_DIR.parent
HIGH_COST_INTEGRATION_MARK = pytest.mark.integration_high_cost
DEFAULT_MARKET_ALERT_TEST_ENV = {
    "PYTEST_RUNNING": "1",
    "FRONTEND_ORIGINS": "http://localhost:5173",
    "DATABASE_URL": "sqlite+pysqlite:///:memory:",
    "SECRET_KEY": "pytest-secret-key",
    "REFRESH_TOKEN_COOKIE_SECURE": "0",
    "REFRESH_TOKEN_COOKIE_SAMESITE": "lax",
    "TEMPORAL_HEALTH_MAX_ATTEMPTS": "1",
    "TEMPORAL_HEALTH_TIMEOUT": "1",
    "TEMPORAL_HEALTH_CHECK_INTERVAL": "1",
    "TEMPORAL_HOST": "localhost",
    "TEMPORAL_PORT": "7233",
    "TEMPORAL_NAMESPACE": "default",
    "REDIS_HOST": "localhost",
    "REDIS_PORT": "6379",
    "REDIS_PASSWORD": "",
    "REDIS_BROKER_DB": "15",
    "REDIS_RESULT_DB": "14",
    "REDIS_OPERATIONAL_DB": "13",
    "CELERY_BROKER_URL": "redis://localhost:6379/15",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/14",
    "LOG_LEVEL": "WARNING",
    "LOG_FORMAT": "text",
}
_PAYLOAD_SEQUENCE = count()


def _reload_module(module_name: str):
    module = sys.modules.get(module_name)
    if module is None:
        return importlib.import_module(module_name)
    return importlib.reload(module)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _seed_market_alert_test_env() -> None:
    os.environ.pop("SERVICE_NAME", None)
    os.environ.pop("ENV_FILE", None)
    for key, value in DEFAULT_MARKET_ALERT_TEST_ENV.items():
        os.environ.setdefault(key, value)


_seed_market_alert_test_env()


@pytest.fixture(scope="session")
def market_alert_test_paths() -> MappingProxyType[str, Path]:
    return MappingProxyType(
        {
            "module": MARKET_ALERT_DIR,
            "tests": TESTS_DIR,
            "factories": TESTS_DIR / "factories",
        }
    )


@pytest.fixture
def env_override(monkeypatch: pytest.MonkeyPatch):
    def _apply(**overrides: str | int | None) -> None:
        for key, value in overrides.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
                continue
            monkeypatch.setenv(key, str(value))

    return _apply


@pytest.fixture
def reload_market_alert_modules():
    def _reload(*module_names: str) -> dict[str, object]:
        names = module_names or (
            "shared.core.config_base",
            "market_alert.core.config_alert",
        )
        return {module_name: _reload_module(module_name) for module_name in names}

    return _reload


@pytest.fixture
def fresh_market_alert_settings(env_override, reload_market_alert_modules):
    def _factory(**overrides: str | int | None):
        env_override(**DEFAULT_MARKET_ALERT_TEST_ENV)
        if overrides:
            env_override(**overrides)

        modules = reload_market_alert_modules(
            "shared.core.config_base",
            "market_alert.core.config_alert",
        )
        return modules["market_alert.core.config_alert"].settings

    return _factory


@pytest.fixture(scope="session")
def high_cost_integration_marker() -> pytest.MarkDecorator:
    return HIGH_COST_INTEGRATION_MARK


@pytest.fixture
def build_user_payload():
    def _build(**overrides):
        index = next(_PAYLOAD_SEQUENCE)
        payload = {
            "id": uuid4(),
            "name": f"Test User {index}",
            "email": f"user{index}@example.com",
            "phone_number": f"+551199999{index:04d}",
            "password": "StrongPass123",
            "is_active": True,
            "email_verified": True,
            "email_verified_at": _utcnow(),
            "phone_number_verified": False,
            "phone_verified_at": None,
            "status": "active",
            "role": "user",
            "last_login": None,
            "created_date": _utcnow(),
            "updated_date": _utcnow(),
        }
        payload.update(overrides)
        return payload

    return _build


@pytest.fixture
def build_monitored_product_payload():
    def _build(**overrides):
        index = next(_PAYLOAD_SEQUENCE)
        created_at = _utcnow()
        payload = {
            "id": uuid4(),
            "owner_id": uuid4(),
            "display_name": f"Monitorado {index}",
            "name": f"Monitorado {index}",
            "url": f"https://store.example.com/products/{index}",
            "normalized_url": f"https://store.example.com/products/{index}",
            "current_price": Decimal("199.90"),
            "currency": "BRL",
            "source": "monitored",
            "availability": True,
            "last_status": "collected",
            "display_status": "competitive",
            "thumbnail": "https://cdn.example.com/images/monitorado.png",
            "created_at": created_at,
            "last_scraped_at": _utcnow(),
            "last_collected_at": _utcnow(),
            "next_check_at": _utcnow(),
            "last_price_change_at": _utcnow(),
            "stability": "stable",
            "monitored_since": created_at,
            "last_price_change_global_at": _utcnow(),
            "competitiveness_status": "competitive",
            "is_featured": False,
            "paused": False,
            "paused_at": None,
            "comparison_summary": None,
        }
        payload.update(overrides)
        return payload

    return _build


@pytest.fixture
def build_competitor_product_payload():
    def _build(**overrides):
        index = next(_PAYLOAD_SEQUENCE)
        payload = {
            "id": uuid4(),
            "monitored_product_id": uuid4(),
            "display_name": f"Concorrente {index}",
            "name": f"Concorrente {index}",
            "url": f"https://competitor.example.com/products/{index}",
            "current_price": Decimal("189.90"),
            "currency": "BRL",
            "source": "competitor",
            "availability": True,
            "last_status": "collected",
            "last_checked": _utcnow(),
            "last_scraped_at": _utcnow(),
            "is_paused": False,
            "thumbnail": "https://cdn.example.com/images/concorrente.png",
        }
        payload.update(overrides)
        return payload

    return _build


@pytest.fixture
def build_comparison_snapshot():
    def _build(**overrides):
        payload = {
            "monitored_price": Decimal("199.90"),
            "competitor_prices": [
                Decimal("189.90"),
                Decimal("194.90"),
                Decimal("205.00"),
            ],
            "competitor_availability": [True, True, True],
        }
        payload.update(overrides)
        return ComparisonSnapshot(**payload)

    return _build


@pytest.fixture
def user_payload(build_user_payload):
    return build_user_payload()


@pytest.fixture
def monitored_product_payload(build_monitored_product_payload):
    return build_monitored_product_payload()


@pytest.fixture
def competitor_product_payload(build_competitor_product_payload, monitored_product_payload):
    return build_competitor_product_payload(
        monitored_product_id=monitored_product_payload["id"]
    )


@pytest.fixture
def comparison_snapshot(build_comparison_snapshot):
    return build_comparison_snapshot()


@pytest.fixture
def build_request():
    def _build(
        *,
        method: str = "GET",
        path: str = "/",
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        client: tuple[str, int] = ("127.0.0.1", 12345),
    ) -> Request:
        request_headers = dict(headers or {})
        if cookies:
            request_headers["cookie"] = "; ".join(
                f"{key}={value}" for key, value in cookies.items()
            )

        raw_headers = [
            (key.lower().encode("latin-1"), str(value).encode("latin-1"))
            for key, value in request_headers.items()
        ]

        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "headers": raw_headers,
            "client": client,
        }
        return Request(scope)

    return _build
