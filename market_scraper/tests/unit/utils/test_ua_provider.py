""" Testes para o provider de User-Agent com rotação configurável. """

from __future__ import annotations

from typing import List

import pytest

from market_scraper.core.config_scraper import settings
from market_scraper.utils import ua_provider


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante que cada teste utiliza configurações isoladas."""

    monkeypatch.setattr(settings, "SCRAPER_USER_AGENT_STATIC_POOL", ("UA1", "UA2", "UA3"))
    monkeypatch.setattr(settings, "SCRAPER_USER_AGENT_DEFAULT", "UA1")
    monkeypatch.setattr(settings, "SCRAPER_USER_AGENT_ROTATION_STRATEGY", "per_request")
    monkeypatch.setattr(settings, "SCRAPER_FAKE_UA_CACHE_TTL_SECONDS", 10)
    monkeypatch.setattr(settings, "SCRAPER_FAKE_UA_CACHE_MAX_SIZE", 4)
    monkeypatch.setattr(settings, "SCRAPER_FAKE_UA_FETCH_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(settings, "SCRAPER_USE_FAKE_USERAGENT", True)

    ua_provider.reset_provider_state()


def _collect_agents(count: int, **kwargs) -> List[str]:
    """Auxiliar para coletar múltiplos resultados do provider."""

    return [ua_provider.get_user_agent("https://exemplo.com", **kwargs) for _ in range(count)]


def test_per_request_rotation_cycles_pool() -> None:
    """Valida round-robin quando configurado como rotação por requisição."""

    result = _collect_agents(4)
    assert result == ["UA1", "UA2", "UA3", "UA1"]


def test_per_session_strategy_persists_for_session_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante afinidade de UA por sessão quando a estratégia assim define."""

    monkeypatch.setattr(settings, "SCRAPER_USER_AGENT_ROTATION_STRATEGY", "per_session")
    ua_provider.reset_provider_state()

    first = ua_provider.get_user_agent("https://dominio.com", session_id="sessao-1")
    again = ua_provider.get_user_agent("https://dominio.com", session_id="sessao-1")
    other = ua_provider.get_user_agent("https://dominio.com", session_id="sessao-2")

    assert first == again == "UA1"
    assert other == "UA2"


def test_per_domain_strategy_uses_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    """Confere que domínios distintos recebem User-Agents fixos próprios."""

    monkeypatch.setattr(settings, "SCRAPER_USER_AGENT_ROTATION_STRATEGY", "per_domain")
    ua_provider.reset_provider_state()

    first = ua_provider.get_user_agent("https://primeiro.com/produto")
    second = ua_provider.get_user_agent("primeiro.com")
    other = ua_provider.get_user_agent("https://segundo.com")

    assert first == second == "UA1"
    assert other == "UA2"


def test_fallback_to_default_when_pool_and_fake_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retorna UA padrão quando pool está vazio e fake-useragent falha."""

    monkeypatch.setattr(settings, "SCRAPER_USER_AGENT_STATIC_POOL", tuple())
    monkeypatch.setattr(settings, "SCRAPER_USER_AGENT_DEFAULT", "DEFAULT-UA")
    ua_provider.reset_provider_state()

    monkeypatch.setattr(ua_provider, "_fetch_fake_user_agent_with_timeout", lambda: None)

    ua = ua_provider.get_user_agent("https://site.com")
    assert ua == "DEFAULT-UA"


def test_fake_user_agent_cache_reuses_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica que o cache do fake-useragent evita chamadas repetidas."""

    monkeypatch.setattr(settings, "SCRAPER_USER_AGENT_STATIC_POOL", tuple())
    monkeypatch.setattr(settings, "SCRAPER_USER_AGENT_DEFAULT", "DEFAULT-UA")
    ua_provider.reset_provider_state()

    calls: List[int] = []

    def _fake_loader() -> str:
        calls.append(1)
        return "FAKE-UA"

    monkeypatch.setattr(ua_provider, "_fetch_fake_user_agent_with_timeout", _fake_loader)

    first = ua_provider.get_user_agent("https://a.com")
    second = ua_provider.get_user_agent("https://b.com")

    assert first == second == "FAKE-UA"
    assert len(calls) == 1

def test_fake_user_agent_disabled_skips_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Confere que não acionamos o fake-useragent quando a flag está desativada."""

    monkeypatch.setattr(settings, "SCRAPER_USER_AGENT_STATIC_POOL", tuple())
    monkeypatch.setattr(settings, "SCRAPER_USER_AGENT_DEFAULT", "DEFAULT-UA")
    monkeypatch.setattr(settings, "SCRAPER_USE_FAKE_USERAGENT", False)
    ua_provider.reset_provider_state()

    def _unexpected_call() -> str:
        raise AssertionError("fake-useragent não deve ser consultado")

    monkeypatch.setattr(ua_provider, "_fetch_fake_user_agent_with_timeout", _unexpected_call)

    ua = ua_provider.get_user_agent("https://bloqueado.com")
    assert ua == "DEFAULT-UA"
    