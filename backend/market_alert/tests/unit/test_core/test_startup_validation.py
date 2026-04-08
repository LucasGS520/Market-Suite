""" Testes unitarios para configuracao e validacao de startup. """

from __future__ import annotations

import os
import random

import pytest
from pydantic import ValidationError

from market_alert.infrastructure import startup_validation


pytestmark = pytest.mark.unit


def test_settings_builds_operational_redis_url_from_env(fresh_market_alert_settings) -> None:
    settings = fresh_market_alert_settings(
        FRONTEND_ORIGINS="http://localhost:5173",
        REDIS_HOST="redis-test",
        REDIS_PORT="6380",
        REDIS_PASSWORD="secret",
        REDIS_OPERATIONAL_DB="9",
    )

    assert settings.redis_operational_url == "redis://:secret@redis-test:6380/9"


def test_settings_require_frontend_origins(fresh_market_alert_settings) -> None:
    with pytest.raises(ValidationError, match="FRONTEND_ORIGINS"):
        fresh_market_alert_settings(FRONTEND_ORIGINS="")


def test_settings_require_frontend_origin_scheme(fresh_market_alert_settings) -> None:
    with pytest.raises(ValidationError, match="http:// ou https://"):
        fresh_market_alert_settings(FRONTEND_ORIGINS="frontend.local")


def test_fresh_market_alert_settings_ignore_env_file_in_pytest(
    fresh_market_alert_settings,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENV_FILE", "ignored-by-tests.env")

    settings = fresh_market_alert_settings()

    assert os.environ["ENV_FILE"] == "ignored-by-tests.env"
    assert settings.FRONTEND_ORIGINS == "http://localhost:5173"
    assert settings.SECRET_KEY == "pytest-secret-key"


def test_validate_startup_dependencies_returns_true_when_all_checks_pass(monkeypatch) -> None:
    monkeypatch.setattr(startup_validation, "_validate_postgres", lambda: True)
    monkeypatch.setattr(startup_validation, "_validate_redis", lambda: True)
    monkeypatch.setattr(startup_validation, "_validate_temporal", lambda: None)

    assert startup_validation.validate_startup_dependencies(strict=True) is True


def test_validate_startup_dependencies_returns_false_when_non_strict(monkeypatch) -> None:
    monkeypatch.setattr(startup_validation, "_validate_postgres", lambda: False)
    monkeypatch.setattr(startup_validation, "_validate_redis", lambda: True)
    monkeypatch.setattr(startup_validation, "_validate_temporal", lambda: None)

    assert startup_validation.validate_startup_dependencies(strict=False) is False


def test_validate_startup_dependencies_raises_when_strict_and_dependency_fails(monkeypatch) -> None:
    monkeypatch.setattr(startup_validation, "_validate_postgres", lambda: False)
    monkeypatch.setattr(startup_validation, "_validate_redis", lambda: True)
    monkeypatch.setattr(startup_validation, "_validate_temporal", lambda: None)

    with pytest.raises(RuntimeError, match="Falha na valida"):
        startup_validation.validate_startup_dependencies(strict=True)


def test_build_temporal_delays_uses_exponential_backoff_without_jitter_when_mocked(monkeypatch) -> None:
    monkeypatch.setattr(random, "uniform", lambda start, end: 0)

    delays = startup_validation._build_temporal_delays(5)

    assert delays == [2, 4, 8, 16, 30]
