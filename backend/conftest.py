from __future__ import annotations

import os
import sys
from pathlib import Path
from types import MappingProxyType

import pytest


BACKEND_DIR = Path(__file__).resolve().parent
MARKET_ALERT_DIR = BACKEND_DIR / "market_alert"
MARKET_ALERT_TEST_ENV_FILE = MARKET_ALERT_DIR / ".env.market_alert.test"

DEFAULT_TEST_ENV = {
    "ENV_FILE": str(Path("market_alert") / ".env.market_alert.test"),
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


def _ensure_backend_on_path() -> None:
    backend_dir = str(BACKEND_DIR)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)


def _seed_backend_test_env() -> None:
    if not MARKET_ALERT_TEST_ENV_FILE.exists():
        raise RuntimeError(
            "Arquivo de ambiente de teste ausente: "
            f"{MARKET_ALERT_TEST_ENV_FILE}"
        )

    os.environ.pop("SERVICE_NAME", None)
    for key, value in DEFAULT_TEST_ENV.items():
        os.environ.setdefault(key, value)


_ensure_backend_on_path()
_seed_backend_test_env()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        node_path = str(item.fspath).replace("\\", "/")
        if "/tests/unit/" in node_path and "unit" not in item.keywords:
            item.add_marker(pytest.mark.unit)
        if "/tests/integration/" in node_path and "integration" not in item.keywords:
            item.add_marker(pytest.mark.integration)
        if "/tests/stress/" in node_path and "stress" not in item.keywords:
            item.add_marker(pytest.mark.stress)


@pytest.fixture(scope="session")
def backend_test_paths() -> MappingProxyType[str, Path]:
    return MappingProxyType(
        {
            "backend": BACKEND_DIR,
            "market_alert": MARKET_ALERT_DIR,
            "market_alert_env_file": MARKET_ALERT_TEST_ENV_FILE,
        }
    )


@pytest.fixture(scope="session")
def backend_test_env_defaults() -> MappingProxyType[str, str]:
    return MappingProxyType(dict(DEFAULT_TEST_ENV))
