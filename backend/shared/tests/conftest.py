from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import MappingProxyType

import pytest


TESTS_DIR = Path(__file__).resolve().parent
MODULE_DIR = TESTS_DIR.parent
BACKEND_DIR = MODULE_DIR.parent
SHARED_TEST_ENV_FILE = MODULE_DIR / ".env.shared.test"

DEFAULT_SHARED_TEST_ENV = {
    "ENV_FILE": str(Path("shared") / ".env.shared.test"),
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
    if not SHARED_TEST_ENV_FILE.exists():
        raise RuntimeError(
            "Arquivo de ambiente de teste ausente: "
            f"{SHARED_TEST_ENV_FILE}"
        )

    os.environ.pop("SERVICE_NAME", None)
    os.environ["ENV_FILE"] = DEFAULT_SHARED_TEST_ENV["ENV_FILE"]
    for key, value in DEFAULT_SHARED_TEST_ENV.items():
        if key == "ENV_FILE":
            continue
        os.environ.setdefault(key, value)


def _reset_loaded_runtime_state() -> None:
    redis_client_module = sys.modules.get("shared.utils.redis_client")
    if redis_client_module is not None:
        thread_local = getattr(redis_client_module, "_thread_local", None)
        if thread_local is not None:
            for attr in ("client", "operational_client"):
                client = getattr(thread_local, attr, None)
                if client is not None and hasattr(client, "close"):
                    client.close()
                if hasattr(thread_local, attr):
                    delattr(thread_local, attr)
        getattr(redis_client_module, "_registered_scripts", {}).clear()
        getattr(redis_client_module, "_registered_token_bucket_scripts", {}).clear()

    task_dispatcher_module = sys.modules.get("shared.clients.celery.task_dispatcher")
    if task_dispatcher_module is not None:
        task_dispatcher_module._sender = None

    scraper_client_module = sys.modules.get("shared.clients.scraper.scraper_client")
    if scraper_client_module is not None:
        scraper_client_module._rate_limiter_inst = None
        scraper_client_module._circuit_breaker_inst = None

    database_module = sys.modules.get("shared.infra.db.database")
    if database_module is not None:
        engine = getattr(database_module, "engine", None)
        if engine is not None and hasattr(engine, "dispose"):
            engine.dispose()


_ensure_backend_on_path()
_seed_shared_test_env()


@pytest.fixture(scope="session")
def shared_test_paths() -> MappingProxyType[str, Path]:
    return MappingProxyType(
        {
            "backend": BACKEND_DIR,
            "module": MODULE_DIR,
            "tests": TESTS_DIR,
            "env_file": SHARED_TEST_ENV_FILE,
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
