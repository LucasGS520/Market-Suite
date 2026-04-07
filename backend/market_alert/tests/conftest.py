from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import MappingProxyType

import pytest
from fastapi import Request

from market_alert.tests.factories import (
    ComparisonSnapshotFactory,
    CompetitorProductPayloadFactory,
    MonitoredProductPayloadFactory,
    UserPayloadFactory,
)


TESTS_DIR = Path(__file__).resolve().parent
MARKET_ALERT_DIR = TESTS_DIR.parent
HIGH_COST_INTEGRATION_MARK = pytest.mark.integration_high_cost


def _reload_module(module_name: str):
    module = sys.modules.get(module_name)
    if module is None:
        return importlib.import_module(module_name)
    return importlib.reload(module)


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
    return UserPayloadFactory.build


@pytest.fixture
def build_monitored_product_payload():
    return MonitoredProductPayloadFactory.build


@pytest.fixture
def build_competitor_product_payload():
    return CompetitorProductPayloadFactory.build


@pytest.fixture
def build_comparison_snapshot():
    return ComparisonSnapshotFactory.build


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
