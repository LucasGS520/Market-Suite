from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import MappingProxyType

import pytest


TESTS_DIR = Path(__file__).resolve().parent
MODULE_DIR = TESTS_DIR.parent
ORCHESTRATOR_TEST_ENV_FILE = MODULE_DIR / ".env.market_orchestrator.test"
HIGH_COST_INTEGRATION_MARK = pytest.mark.integration_high_cost

DEFAULT_ORCHESTRATOR_TEST_ENV = {
    "PYTEST_RUNNING": "1",
    "ENV_FILE": str(Path("market_orchestrator") / ".env.market_orchestrator.test"),
}


def _reload_module(module_name: str):
    module = sys.modules.get(module_name)
    if module is None:
        return importlib.import_module(module_name)
    return importlib.reload(module)


def _seed_orchestrator_test_env() -> None:
    if not ORCHESTRATOR_TEST_ENV_FILE.exists():
        raise RuntimeError(
            "Arquivo de ambiente de teste ausente: "
            f"{ORCHESTRATOR_TEST_ENV_FILE}"
        )

    for key, value in DEFAULT_ORCHESTRATOR_TEST_ENV.items():
        os.environ.setdefault(key, value)


_seed_orchestrator_test_env()


@pytest.fixture(scope="session")
def orchestrator_test_paths() -> MappingProxyType[str, Path]:
    return MappingProxyType(
        {
            "module": MODULE_DIR,
            "tests": TESTS_DIR,
            "env_file": ORCHESTRATOR_TEST_ENV_FILE,
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
