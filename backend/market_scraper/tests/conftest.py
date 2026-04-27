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

DEFAULT_SCRAPER_TEST_ENV = {
    "PYTEST_RUNNING": "1",
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
    "SCRAPER_CACHE_TTL_SECONDS": "60",
    "SCRAPER_CACHE_MAX_ENTRIES": "32",
    "SCRAPER_STEP_TIMEOUT_SECONDS": "2.0",
    "SCRAPER_PIPELINE_TIMEOUT_SECONDS": "3.0",
    "SCRAPER_SINGLEFLIGHT_LOCK_TTL": "2.0",
    "SCRAPER_SINGLEFLIGHT_MAX_ENTRIES": "32",
    "SCRAPER_HTTP_TIMEOUT_CONNECT": "0.5",
    "SCRAPER_HTTP_TIMEOUT_READ": "0.5",
    "SCRAPER_HTTP_TIMEOUT_WRITE": "0.5",
    "SCRAPER_HTTP_TIMEOUT_POOL": "0.5",
    "SCRAPER_HTTP_RETRIES": "0",
    "SCRAPER_HTTP_RETRY_BACKOFF_BASE": "0.1",
    "SCRAPER_HTTP_MAX_REDIRECTS": "2",
    "SCRAPER_HTTP_MAX_CONNECTIONS": "4",
    "SCRAPER_HTTP_MAX_KEEPALIVE": "2",
    "SCRAPER_HTTP_MAX_CONTENT_LENGTH": "250000",
    "SCRAPER_DNS_TIMEOUT": "0.5",
    "SCRAPER_DNS_CACHE_TTL": "5.0",
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
    os.environ.pop("SERVICE_NAME", None)
    os.environ.pop("ENV_FILE", None)
    for key, value in DEFAULT_SCRAPER_TEST_ENV.items():
        os.environ.setdefault(key, value)


def _reset_loaded_runtime_state() -> None:
    cache_module = sys.modules.get("market_scraper.infra.cache.cache")
    if cache_module is not None:
        cache_module.clear()

    singleflight_module = sys.modules.get("market_scraper.infra.cache.singleflight")
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
            "market_scraper.infra.cache.cache",
            "market_scraper.infra.cache.singleflight",
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
            "market_scraper.infra.cache.cache",
            "market_scraper.infra.cache.singleflight",
        )
        _reset_loaded_runtime_state()
        return modules["market_scraper.core.config_scraper"].settings

    return _factory


@pytest.fixture(autouse=True)
def reset_scraper_runtime_state():
    _reset_loaded_runtime_state()
    yield
    _reset_loaded_runtime_state()
