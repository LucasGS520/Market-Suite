from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import MappingProxyType

import pytest
from tests_runtime import reset_shared_runtime_state as reset_shared_runtime


TESTS_DIR = Path(__file__).resolve().parent
MODULE_DIR = TESTS_DIR.parent
BACKEND_DIR = MODULE_DIR.parent

DEFAULT_SHARED_TEST_ENV = {
    "PYTEST_RUNNING": "1",
    "DATABASE_URL": "sqlite+pysqlite:///:memory:",
    "REDIS_HOST": "localhost",
    "REDIS_PORT": "6379",
    "REDIS_DB": "12",
    "REDIS_PASSWORD": "",
    "REDIS_BROKER_DB": "15",
    "REDIS_RESULT_DB": "14",
    "REDIS_OPERATIONAL_DB": "13",
    "CELERY_BROKER_URL": "redis://localhost:6379/15",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/14",
    "TEMPORAL_HOST": "localhost",
    "TEMPORAL_PORT": "7233",
    "TEMPORAL_NAMESPACE": "default",
    "TEMPORAL_TASK_QUEUE": "market-orchestrator-test",
    "LOG_LEVEL": "WARNING",
    "LOG_FORMAT": "text",
}


def _ensure_backend_on_path() -> None:
    backend_dir = str(BACKEND_DIR)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)


def _reload_module(module_name: str):
    module = sys.modules.get(module_name)
    if module is None:
        return importlib.import_module(module_name)
    return importlib.reload(module)


def _seed_shared_test_env() -> None:
    os.environ.pop("SERVICE_NAME", None)
    os.environ.pop("ENV_FILE", None)
    for key, value in DEFAULT_SHARED_TEST_ENV.items():
        os.environ.setdefault(key, value)


def _reset_loaded_runtime_state() -> None:
    reset_shared_runtime()


_ensure_backend_on_path()
_seed_shared_test_env()


@pytest.fixture(scope="session")
def shared_test_paths() -> MappingProxyType[str, Path]:
    return MappingProxyType(
        {
            "backend": BACKEND_DIR,
            "module": MODULE_DIR,
            "tests": TESTS_DIR,
        }
    )


@pytest.fixture(scope="session")
def shared_test_env_defaults() -> MappingProxyType[str, str]:
    return MappingProxyType(dict(DEFAULT_SHARED_TEST_ENV))


@pytest.fixture
def env_override(monkeypatch: pytest.MonkeyPatch):
    def _apply(**overrides: str | int | float | None) -> None:
        for key, value in overrides.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
                continue
            monkeypatch.setenv(key, str(value))

    return _apply


@pytest.fixture(autouse=True)
def reset_shared_runtime_state():
    _reset_loaded_runtime_state()
    yield
    _reset_loaded_runtime_state()


@pytest.fixture
def reload_shared_modules():
    def _reload(*module_names: str) -> dict[str, object]:
        names = module_names or (
            "shared.core.config_base",
            "shared.utils.redis_client",
            "shared.utils.redis_locks",
            "shared.infra.db.database",
            "shared.infra.redis_pubsub",
            "shared.clients.celery.task_dispatcher",
            "shared.clients.scraper.scraper_client",
            "shared.clients.temporal.orchestrator_client",
        )
        return {module_name: _reload_module(module_name) for module_name in names}

    return _reload


@pytest.fixture
def fresh_shared_settings(
    env_override,
    reload_shared_modules,
    shared_test_env_defaults,
):
    def _factory(**overrides: str | int | float | None):
        env_override(**dict(shared_test_env_defaults))
        if overrides:
            env_override(**overrides)

        modules = reload_shared_modules("shared.core.config_base")
        return modules["shared.core.config_base"].ConfigBase()

    return _factory
