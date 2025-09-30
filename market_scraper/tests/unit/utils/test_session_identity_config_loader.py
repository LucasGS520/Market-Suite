""" Testes do carregamento das políticas de identidade de sessão via YAML """
from __future__ import annotations

import importlib
import os
import time
import textwrap
from pathlib import Path

import pytest

import market_scraper.utils_controllers.configuration.session_identity_config as identity_config


@pytest.fixture()
def reload_identity_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """ Força o recarregamento do módulo aplicando variáveis de ambiente temporariamente """
    def _reload(content: str | None = None, **env: str | None):
        config_path = tmp_path / "session_identity.yaml"
        if content is not None:
            config_path.write_text(content, encoding="utf-8")
        env.setdefault("SESSION_IDENTITY_CONFIG_FILE", str(config_path))
        for key, value in env.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)
        module = importlib.reload(identity_config)
        return module, config_path
    
    yield _reload
    importlib.reload(identity_config)

def test_policy_padrao_carregada_sem_erros() -> None:
    """ Garante que a política padrão definida no repositório é carregada corretamente """
    policy = identity_config.settings.policy_for("mercadolivre.com.br")

    assert isinstance(policy, identity_config.SessionIdentityPolicy)
    assert policy.user_agent.max_requests > 0
    assert policy.cookie_template.template

def test_arquivo_inexistente_retorna_defaults(reload_identity_config) -> None:
    """ Verifica que políticas seguras são usadas quando o YAML não disponível """
    module, config_path = reload_identity_config(content=None)
    if config_path.exists():
        os.remove(config_path)

    policy = module.settings.policy_for("dominio.com")

    assert policy.user_agent.max_requests == 50
    assert policy.user_agent.session_timeout == 3600

def test_reload_forca_releitura(reload_identity_config) -> None:
    """ Garante que ``settings.reload`` limpa o cache mesmo sem hot-reload ativo """

    first_content = textwrap.dedent(
        """
        defaults:
          user_agent:
            max_requests: 2
            session_timeout: 90
        """
    )
    
    module, path = reload_identity_config(content=first_content)
    assert module.settings.policy_for("site.com").user_agent.max_requests == 2

    path.write_text(
        textwrap.dedent(
            """
            defaults:
              user_agent:
                max_requests: 8
                session_timeout: 300
            """
        ),
        encoding="utf-8",
    )

    reloaded_policy = module.settings.reload().policy_for("site.com")
    assert reloaded_policy.user_agent.max_requests == 8
    assert reloaded_policy.user_agent.session_timeout == 300

def test_pipeline_personalizada_por_ambiente(reload_identity_config) -> None:
    """ Confirma que caminhos customizados são respeitados e retornam novos valores """
    yaml_content = textwrap.dedent(
        """
        defaults:
          user_agent:
            max_requests: 5
            session_timeout: 120
          cookies:
            template:
              token: abc
        domains:
          exemplo.com:
            user_agent:
              max_requests: 7
        """
    )

    module, _ = reload_identity_config(content=yaml_content)

    defaults_policy = module.settings.policy_for(None)
    assert defaults_policy.cookie_template.template["token"] == "abc"

    policy = module.settings.policy_for("exemplo.com")
    assert policy.user_agent.max_requests == 7
    assert policy.cookie_template.template

def test_politicas_invalidas_sao_ignoradas(reload_identity_config) -> None:
    """ Assegura que dados incorretos no YAML não quebrem o carregamento """
    yaml_content = textwrap.dedent(
        """
        defaults:
          user_agent:
            max_requests: dez
            session_timeout: nul
          cookies:
            template: 123
        domains:
          exemplo.com:
            cookies: []
        """
    )

    module, _ = reload_identity_config(content=yaml_content)

    policy = module.settings.policy_for("exemplo.com")
    assert policy.user_agent.max_requests == 50
    assert policy.user_agent.session_timeout == 3600
    assert policy.cookie_template.template

def test_hot_reload_aplica_alteracoes(reload_identity_config) -> None:
    """ Valida que hot-reload atualiza as políticas após alteração do arquivo """
    yaml_content = textwrap.dedent(
        """
        defaults:
          user_agent:
            max_requests: 4
            session_timeout: 120
        """
    )

    module, path = reload_identity_config(
        content=yaml_content, SESSION_IDENTITY_CONFIG_HOT_RELOAD="1"
    )

    assert module.settings.policy_for("site.com").user_agent.max_requests == 4

    time.sleep(0.05)
    path.write_text(
        textwrap.dedent(
            """
            defaults:
              user_agent:
                max_requests: 9
                session_timeout: 240
            """
        ),
        encoding="utf-8",
    )
    os.utime(path, None)

    updated_policy = module.settings.policy_for("site.com")
    assert updated_policy.user_agent.max_requests == 9
    assert updated_policy.user_agent.session_timeout == 240
    