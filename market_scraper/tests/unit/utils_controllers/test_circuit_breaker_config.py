""" Teste do carregador de configurações do Circuit Breaker """

from __future__ import annotations
 
import importlib
import os
import textwrap
import time
from pathlib import Path

import pytest

from market_scraper.utils_controllers.configuration import circuit_breaker_config as config


@pytest.fixture(autouse=True)
def cleanup_environment(monkeypatch: pytest.MonkeyPatch):
    """ Garante isolamento entre cenários de teste removendo efeitos colaterais """
    yield
    monkeypatch.delenv("CIRCUIT_CONFIG_FILE", raising=False)
    monkeypatch.delenv("CIRCUIT_BREAKER_CONFIG_HOT_RELOAD", raising=False)
    importlib.reload(config)

def test_policy_for_returns_domain_specific_policy() -> None:
    """ Garante que a política específica é aplicada quando o domínio corresponde """
    defaults = config.CircuitBreakerPolicy(failure_threshold=5, recovery_time=300)
    domain_policy = config.CircuitBreakerPolicy(failure_threshold=2, recovery_time=120)
    settings = config.CircuitBreakerSettings(defaults=defaults, domains={"loja.com": domain_policy})

    assert settings.policy_for("api.loja.com") == domain_policy
    assert settings.policy_for("LOJA.COM") == domain_policy
    assert settings.policy_for(None) == defaults
    assert settings.policy_for("outro.com") == defaults

def test_build_settings_normalizes_domains() -> None:
    """ Valida a construção das configurações e normalização dos domínios """
    settings = config._build_settings(
        {
            "defaults": {"failure_threshold": 9, "recovery_time": 600},
            "domains": {
                "Loja.com": {"failure_threshold": 3, "recovery_time": 180},
                123: {"failure_threshold": 1, "recovery_time": 60},
            },
        }
    )

    assert settings.policy_for("LOJA.com").fingerprint() == (3, 180)
    assert settings.policy_for("api.exemplo.com").fingerprint() == (9, 600)

def test_circuit_breaker_module_loads_policies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """ Confirma que a importação pública expõe as politicas esperadas """
    config_file = tmp_path / "circuit_breaker.yaml"
    config_file.write_text(
        textwrap.dedent(
            """
            defaults:
              failure_threshold: 7
              recovery_time: 400
            domains:
              exemplo.com:
                failure_threshold: 4
                recovery_time: 240
            """
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("CIRCUIT_CONFIG_FILE", str(config_file))

    module = importlib.import_module("market_scraper.utils.circuit_breaker")
    module = importlib.reload(module)

    policy = module.circuit_breaker_settings.policy_for("api.exemplo.com")
    assert policy.fingerprint() == (4, 240)

    default_policy = module.circuit_breaker_settings.policy_for("outro-dominio.com")
    assert default_policy.fingerprint() == (7, 400)

def test_hot_reload_detects_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """ Verifica que o hot-reload invalida o cache quando o arquivo é modificado """
    config_file = tmp_path / "circuit_breaker.yaml"
    config_file.write_text(
        "defaults: {failure_threshold: 5, recovery_time: 300}\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("CIRCUIT_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("CIRCUIT_BREAKER_CONFIG_HOT_RELOAD", "1")
    importlib.reload(config)

    settings_a = config.settings.policy_for("foo")
    assert settings_a.fingerprint() == (5, 300)

    time.sleep(0.05)
    config_file.write_text(
        "defaults: {failure_threshold: 6, recovery_time: 120}\n",
        encoding="utf-8",
    )
    os.utime(config_file, None)

    settings_b = config.settings.policy_for("foo")
    assert settings_b.fingerprint() == (6, 120)

def test_policy_from_handles_invalid_entries() -> None:
    """ Garante que valores inválidos são normalizados para defaults seguros """
    policy = config._policy_from({"failure_threshold": "invalid", "recovery_time": None})

    assert policy.failure_threshold == 5
    assert policy.recovery_time == 300

def test_load_settings_ignores_missing_file(monkeypatch, tmp_path) -> None:
    """ Confirma que carregar um arquiv inexistente devolve a política padrão """
    config_path = tmp_path / "missing.yaml"
    monkeypatch.setenv("CIRCUIT_CONFIG_FILE", str(config_path))
    importlib.reload(config)

    settings_obj = config.settings.policy_for("foo")
    assert settings_obj.fingerprint() == (5, 300)

def test_reload_forces_refresh_when_hot_reload_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ Garante que ``settings.reload`` aplica alterações quando hot-reload está inativo """
    config_file = tmp_path / "circuit_breaker.yaml"
    config_file.write_text(
        "defaults: {failure_threshold: 3, recovery_time: 90}\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("CIRCUIT_CONFIG_FILE", str(config_file))
    importlib.reload(config)

    first_policy = config.settings.policy_for("foo")
    assert first_policy.fingerprint() == (3, 90)

    config_file.write_text(
        "defaults: {failure_threshold: 9, recovery_time: 240}\n",
        encoding="utf-8",
    )

    cached_policy = config.settings.policy_for("foo")
    assert cached_policy.fingerprint() == (3, 90)

    refreshed_policy = config.settings.reload().policy_for("foo")
    assert refreshed_policy.fingerprint() == (9, 240)
