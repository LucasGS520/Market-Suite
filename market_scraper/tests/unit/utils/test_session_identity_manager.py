""" Testes para o `SessionIdentityManager` garantindo identidade consistente """

from __future__ import annotations

from typing import Callable

import pytest

from market_scraper.utils.session_identity import SessionIdentityManager
from market_scraper.utils.configuration.session_identity import (
    SessionIdentityPolicy,
    UserAgentConfig,
    CookieTemplateConfig,
)

@pytest.fixture()
def configure_policy(monkeypatch: pytest.MonkeyPatch) -> Callable[..., SessionIdentityPolicy]:
    """ Aplica política customizada devolvendo função auxiliar para os testes """
    def _apply(max_requests: int = 2, session_timeout: int = 10, template: dict[str, str] | None = None) -> SessionIdentityPolicy:
        policy = SessionIdentityPolicy(
            user_agent=UserAgentConfig(max_requests=max_requests, session_timeout=session_timeout),
            cookies=CookieTemplateConfig(template=template or {}),
        )
        monkeypatch.setattr("market_scraper.utils.session_identity.identity_settings.policy_for", lambda host: policy)
        return policy
    
    return _apply

@pytest.fixture()
def manager() -> SessionIdentityManager:
    """ Instância isolada do gerenciador para cada teste """
    return SessionIdentityManager()

def test_user_agent_persiste_ate_limite(configure_policy, manager: SessionIdentityManager) -> None:
    """ Deve reutilizar o mesmo User-Agent enquanto não atingir o limite """
    configure_policy(max_requests=3)
    primeiro = manager.get_user_agent("sessao", host="example.com")
    segundo = manager.get_user_agent("sessao", host="example.com")
    assert primeiro == segundo

def test_user_agent_rotaciona_apos_limite(monkeypatch: pytest.MonkeyPatch, configure_policy, manager: SessionIdentityManager) -> None:
    """ Deve reutilizar o mesmo User-Agent enquanto não atinge o limite """
    configure_policy(max_requests=2)
    uas = iter(["UA-1", "UA-2"])
    monkeypatch.setattr("market_scraper.utils.session_identity.random.choice", lambda seq: next(uas))

    assert manager.get_user_agent("sessao", host="example.com") == "UA-1"
    assert manager.get_user_agent("sessao", host="example.com") == "UA-1"
    assert manager.get_user_agent("sessao", host="example.com") == "UA-2"

def test_user_agent_rotaciona_apos_timeout(monkeypatch: pytest.MonkeyPatch, configure_policy, manager: SessionIdentityManager) -> None:
    """ Ao expirar o tempo de sessão o User-Agent deve ser renovado automaticamente """
    configure_policy(max_requests=5, session_timeout=5)
    uas = iter(["UA-1", "UA-2"])
    tempos = [0.0, 1.0, 6.0]

    monkeypatch.setattr("market_scraper.utils.session_identity.random.choice", lambda seq: next(uas))
    monkeypatch.setattr("market_scraper.utils.session_identity.time.monotonic", lambda: tempos.pop(0))

    assert manager.get_user_agent("sessao", host="example.com") == "UA-1"
    assert manager.get_user_agent("sessao", host="example.com") == "UA-1"
    assert manager.get_user_agent("sessao", host="example.com") == "UA-2"

def test_cookies_utiliza_template(configure_policy, manager: SessionIdentityManager) -> None:
    """ `get_cookies` deve iniciar com template configurado """
    configure_policy(template={"chave": "valor"})
    jar = manager.get_cookies("sessao", host="example.com")
    assert jar.get("chave") == "valor"

def test_update_cookies_aplica_resposta(configure_policy, manager: SessionIdentityManager) -> None:
    """ Atualizar cookies deve incorporar valores obtidos na resposta HTTP """
    configure_policy()

    class Resposta:
        cookies = {"novo": "valor"}

    jar = manager.get_cookies("sessao", host="example.com")
    manager.update_cookies("sessao", Resposta(), host="example.com")
    assert jar.get("novo") == "valor"

def test_reset_cookies_remove_sessao(configure_policy, manager: SessionIdentityManager) -> None:
    """ Resetar cookies deve limpar o armazenamento da sessão """
    configure_policy()
    manager.get_cookies("sessao", host="example.com")
    manager.reset_cookies("sessao", host="example.com")
    novo = manager.get_cookies("sessao", host="example.com")
    assert novo is not None
    