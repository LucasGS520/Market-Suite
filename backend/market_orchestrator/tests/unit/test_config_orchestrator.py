from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.unit


def test_fresh_orchestrator_settings_ignore_env_file_in_pytest(
    fresh_orchestrator_settings,
    orchestrator_test_paths,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENV_FILE", "ignored-by-tests.env")

    settings = fresh_orchestrator_settings()

    assert "env_file" not in orchestrator_test_paths
    assert os.environ["ENV_FILE"] == "ignored-by-tests.env"
    assert settings.TEMPORAL_TASK_QUEUE == "market-orchestrator-test"
    assert settings.WORKFLOW_HISTORY_LENGTH_LIMIT == 25
