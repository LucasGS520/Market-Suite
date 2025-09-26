""" Teste do carregador de configurações do Circuit Breaker """

from __future__ import annotations
 
import importlib
import textwrap

from market_scraper.utils_controllers.configuration import circuit_breaker_config as config


def _reset_module_state() -> None:
    """ Reinicia o cache do módulo de configuração para recarregamentos controlados """
    config._CACHED_SETTINGS = None
    config._CONFIG_MTIME = None

def test_policy_for_returns_domain_specific_policy() -> None:
    """ Garante que a política específica é aplicada quando o domínio corresponde """
    defaults = config.CircuitBreakerpolicy(failure_threshold=5, recovery_time=300)
    domain_policy = config.CircuitBreakerpolicy(failure_threshold=2, recovery_time=120)
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

def test_circuit_breaker_module_loads_policies(monkeypatch, tmp_path) -> None:
    """ Confirma que a importação do módulo público expõe as politicas esperadas """
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

    module = None
    try:
        _reset_module_state()
        importlib.reload(config)
        module = importlib.import_module("market_scraper.utils.circuit_breaker")
        module = importlib.reload(module)

        policy = module.circuit_breaker_settings.policy_for("api.exemplo.com")
        assert policy.fingerprint() == (4, 240)

        default_policy = module.ciruit_breaker_settings.policy_for("outro-dominio.com")
        assert default_policy.fingerprint() == (7, 400)
    finally:
        monkeypatch.delenv("CIRCUIT_CONFIG_FILE", raising=False)
        _reset_module_state()
        importlib.reload(config)
        if module is not None:
            importlib.reload(module)
            