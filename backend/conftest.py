from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_TEST_ENV = {"PYTEST_RUNNING": "1"}


def _ensure_backend_on_path() -> None:
    backend_dir = str(BACKEND_DIR)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)


def _seed_backend_test_env() -> None:
    os.environ.pop("SERVICE_NAME", None)
    os.environ.pop("ENV_FILE", None)
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
