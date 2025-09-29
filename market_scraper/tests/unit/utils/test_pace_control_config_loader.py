""" Testes focados no carregamento das políticas de pace control via YAML """

from __future__ import annotations

import importlib
import os
import textwrap
from pathlib import Path

import pytest

import market_scraper.utils_controllers.configuration.pace_control_config as pace_config


@pytest.fixture()
def reload_pace_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """ Força o recarregamento do módulo ajustando variáveis de ambiente temporariamente """
    def _reload(content: str | None = None, **env: str | None):
        config_path = tmp_path / "pace_control.yaml"
        if content is not None:
            config_path.write_text(content, encoding="utf-8")
        env.setdefault("PACE_CONTROL_CONFIG_FILE", str(config_path))
        for key, value in env.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.delenv(key, raising=False)
        module = importlib.reload(pace_config)
        return module, config_path
    
    yield _reload
    importlib.reload(pace_config)

def test_settings_policy_for_carrega_yaml_sem_erros() -> None:
    """ Garante que a política carregada para domínio conhecido reflita o YAML """
    policy = pace_config.settings.policy_for("mercadolivre.com.br")

    assert isinstance(policy, pace_config.PaceControlPolicy)
    assert policy.rate_limit is not None
    assert policy.rate_limit.max_requests == 120
    assert policy.rate_limit.window == 60

def test_settings_utiliza_defaults_quando_arquivo_inexistente(
    reload_pace_config,
) -> None:
    """ Confirma que a ausência do arquivo utiliza valores seguros de fallback """
    module, config_path = reload_pace_config(content=None)
    #Remove arquivo caso tenha sido criado automaticamente
    if config_path.exists():
        os.remove(config_path)

    policy = module.settings.policy_for("dominio-inexsistente.com")

    assert isinstance(policy, module.PaceControlPolicy)
    assert policy.rate_limit is not None
    assert policy.token_bucket.rate == pytest.approx(module.scraper_settings.THROTTLE_RATE)

def test_settings_respeita_caminho_personalizado(reload_pace_config) -> None:
    """ Verifica se políticas personalizadas são carregadas via variável de ambiente """
    yaml_content = textwrap.dedent(
        """
        defaults:
          token_bucket:
            rate: 1.5
            capacity: 5
          human_delay:
            avg_wpm: 200
            base_delay: 0.8
        domains:
          exemplo.com:
            token_bucket:
              rate: 2.5
        """
    )

    module, _ = reload_pace_config(content=yaml_content)

    defaults_policy = module.settings.policy_for(None)
    assert defaults_policy.humand_delay.base_delay == pytest.approx(0.8)
    assert defaults_policy.human_delay.avg_wpm == pytest.approx(200)

    domain_policy = module.settings.policy_for("exemplo.com")
    assert domain_policy.token_bucket.rate == pytest.approx(2.5)
    assert domain_policy.human_delay.avg_wpm == pytest.approx(
        module.scraper_settings.HUMAN_AVG_WPM
    )
    assert domain_policy.human_delay.base_delay == pytest.approx(
        module.scraper_settings.HUMAN_BASE_DELAY
    )

def test_settings_ignora_politicas_invalidas(reload_pace_config) -> None:
    """ Certifica que blocos inválidos não derrubem o carregamento do YAML """
    yaml_content = textwrap.dedent(
        """
        defaults:
          rate_limit:
            max_requests: 30
            window: 60
        domains:
          123:
            token_bucket: invalido
          exemplo.com:
            rate_limit:
              max_requests: -5
              window: 0
        """
    )

    module, _ = reload_pace_config(content=yaml_content)

    policy = module.settings.policy_for("sub.exemplo.com")
    assert policy.rate_limit is not None
    assert policy.rate_limit.max_requests == 30
    assert policy.rate_limit.window == 60

def test_settings_hot_reload_atualiza_cache(
    reload_pace_config,
) -> None:
    """ Assegura que alterações no arquivo são refletidas quando o hot-reload está ativo """
    yaml_content = textwrap.dedent(
        """
        defaults:
          token_bucket:
            rate: 1.0
        """
    )

    module, path = reload_pace_config(
        content=yaml_content, PACE_CONTROL_CONFIG_HOT_RELOAD="1"
    )

    assert module.settings.policy_for("qualquer.com").token_bucket.rate == pytest.approx(1.0)

    path.write_text(
        textwrap.dedent(
            """
            defaults:
              token_bucket:
                rate: 3.0
            """
        ),
        encoding="utf-8",
    )
    os.utime(path, None)

    assert module.settings.policy_for("qualquer.com").token_bucket.rate == pytest.approx(3.0)
    