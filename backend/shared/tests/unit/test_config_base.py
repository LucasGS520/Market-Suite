from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.unit


def test_fresh_shared_settings_ignore_env_file_in_pytest(
    fresh_shared_settings,
    shared_test_paths,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENV_FILE", "ignored-by-tests.env")

    settings = fresh_shared_settings()

    assert "env_file" not in shared_test_paths
    assert os.environ["ENV_FILE"] == "ignored-by-tests.env"
    assert settings.REDIS_HOST == "localhost"
    assert settings.LOG_LEVEL == "WARNING"
