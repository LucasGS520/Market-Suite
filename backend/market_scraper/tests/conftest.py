from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path
from types import MappingProxyType

import pytest


TESTS_DIR = Path(__file__).resolve().parent
MODULE_DIR = TESTS_DIR.parent
BACKEND_DIR = MODULE_DIR.parent
SCRAPER_TEST_ENV_FILE = MODULE_DIR / ".env.market_scraper.test"

DEFAULT_SCRAPER_TEST_ENV = {
    "ENV_FILE": str(Path("market_scraper") / ".env.market_scraper.test"),
    "PYTEST_RUNNING": "1",
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


def _seed_scraper_test_env() -> None:
    if not SCRAPER_TEST_ENV_FILE.exists():
        raise RuntimeError(
            "Arquivo de ambiente de teste ausente: "
            f"{SCRAPER_TEST_ENV_FILE}"
        )

    os.environ.pop("SERVICE_NAME", None)
    os.environ["ENV_FILE"] = DEFAULT_SCRAPER_TEST_ENV["ENV_FILE"]
    os.environ.setdefault("PYTEST_RUNNING", DEFAULT_SCRAPER_TEST_ENV["PYTEST_RUNNING"])


def _reset_loaded_runtime_state() -> None:
    cache_module = sys.modules.get("market_scraper.utils.cache")
    if cache_module is not None:
        cache_module.clear()

    singleflight_module = sys.modules.get("market_scraper.utils.singleflight")
    if singleflight_module is not None:
        asyncio.run(singleflight_module.reset())


_ensure_backend_on_path()
_seed_scraper_test_env()


@pytest.fixture(scope="session")
def scraper_test_paths() -> MappingProxyType[str, Path]:
    return MappingProxyType(
        {
            "backend": BACKEND_DIR,
            "module": MODULE_DIR,
            "tests": TESTS_DIR,
            "env_file": SCRAPER_TEST_ENV_FILE,
        }
    )


@pytest.fixture(scope="session")
def scraper_test_env_defaults() -> MappingProxyType[str, str]:
    return MappingProxyType(dict(DEFAULT_SCRAPER_TEST_ENV))


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
def reload_scraper_modules():
    def _reload(*module_names: str) -> dict[str, object]:
        names = module_names or (
            "shared.core.config_base",
            "market_scraper.core.config_scraper",
            "market_scraper.utils.cache",
            "market_scraper.utils.singleflight",
        )
        return {module_name: _reload_module(module_name) for module_name in names}

    return _reload


@pytest.fixture
def fresh_scraper_settings(
    env_override,
    reload_scraper_modules,
    scraper_test_env_defaults,
):
    def _factory(**overrides: str | int | float | None):
        env_override(**dict(scraper_test_env_defaults))
        if overrides:
            env_override(**overrides)

        modules = reload_scraper_modules(
            "shared.core.config_base",
            "market_scraper.core.config_scraper",
            "market_scraper.utils.cache",
            "market_scraper.utils.singleflight",
        )
        _reset_loaded_runtime_state()
        return modules["market_scraper.core.config_scraper"].settings

    return _factory


@pytest.fixture(autouse=True)
def reset_scraper_runtime_state():
    _reset_loaded_runtime_state()
    yield
    _reset_loaded_runtime_state()
