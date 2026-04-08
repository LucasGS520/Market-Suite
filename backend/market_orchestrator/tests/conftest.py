from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import MappingProxyType

import pytest


TESTS_DIR = Path(__file__).resolve().parent
MODULE_DIR = TESTS_DIR.parent
HIGH_COST_INTEGRATION_MARK = pytest.mark.integration_high_cost

DEFAULT_ORCHESTRATOR_TEST_ENV = {
    "PYTEST_RUNNING": "1",
    "DATABASE_URL": "sqlite+pysqlite:///:memory:",
    "TEMPORAL_HOST": "localhost",
    "TEMPORAL_PORT": "7233",
    "TEMPORAL_NAMESPACE": "default",
    "TEMPORAL_TASK_QUEUE": "market-orchestrator-test",
    "WORKFLOW_HISTORY_LENGTH_LIMIT": "25",
    "WORKFLOW_SIGNAL_COUNT_LIMIT": "10",
    "COLLECTION_RESULT_TIMEOUT_SECONDS": "60",
    "COLLECTION_POLL_INTERVAL_SECONDS": "5",
    "RETRY_MAX_ATTEMPTS": "2",
    "RETRY_INITIAL_INTERVAL_SECONDS": "1",
    "RETRY_MAX_INTERVAL_SECONDS": "5",
    "RETRY_BACKOFF_COEFFICIENT": "2.0",
    "ACTIVITY_DISPATCH_TIMEOUT_SECONDS": "5",
    "ACTIVITY_QUERY_STATUS_TIMEOUT_SECONDS": "5",
    "ACTIVITY_PERSIST_SNAPSHOT_TIMEOUT_SECONDS": "5",
    "ACTIVITY_CLEANUP_TIMEOUT_SECONDS": "5",
    "ACTIVITY_FETCH_POLICY_TIMEOUT_SECONDS": "5",
    "SNAPSHOT_KEY_TEMPLATE": "workflow:snapshot:{monitored_id}",
    "SNAPSHOT_TTL_SECONDS": "60",
}


def _reload_module(module_name: str):
    module = sys.modules.get(module_name)
    if module is None:
        return importlib.import_module(module_name)
    return importlib.reload(module)


def _seed_orchestrator_test_env() -> None:
    os.environ.pop("ENV_FILE", None)
    for key, value in DEFAULT_ORCHESTRATOR_TEST_ENV.items():
        os.environ.setdefault(key, value)


_seed_orchestrator_test_env()


@pytest.fixture(scope="session")
def orchestrator_test_paths() -> MappingProxyType[str, Path]:
    return MappingProxyType(
        {
            "module": MODULE_DIR,
            "tests": TESTS_DIR,
        }
    )


@pytest.fixture(scope="session")
def orchestrator_test_env_defaults() -> MappingProxyType[str, str]:
    return MappingProxyType(dict(DEFAULT_ORCHESTRATOR_TEST_ENV))


@pytest.fixture
def env_override(monkeypatch: pytest.MonkeyPatch):
    def _apply(**overrides: str | int | float | None) -> None:
        for key, value in overrides.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
                continue
            monkeypatch.setenv(key, str(value))

    return _apply


@pytest.fixture
def reload_orchestrator_modules():
    def _reload(*module_names: str) -> dict[str, object]:
        names = module_names or ("market_orchestrator.core.config_orchestrator",)
        return {module_name: _reload_module(module_name) for module_name in names}

    return _reload


@pytest.fixture
def fresh_orchestrator_settings(
    env_override,
    reload_orchestrator_modules,
    orchestrator_test_env_defaults,
):
    def _factory(**overrides: str | int | float | None):
        env_override(**dict(orchestrator_test_env_defaults))
        if overrides:
            env_override(**overrides)

        modules = reload_orchestrator_modules(
            "market_orchestrator.core.config_orchestrator",
        )
        return modules["market_orchestrator.core.config_orchestrator"].settings

    return _factory


@pytest.fixture(scope="session")
def high_cost_integration_marker() -> pytest.MarkDecorator:
    return HIGH_COST_INTEGRATION_MARK
