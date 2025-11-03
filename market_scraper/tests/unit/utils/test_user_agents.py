""" Testes para o utilitário central de User-Agent e headers """

import pytest

from market_scraper.core.config_scraper import settings
from market_scraper.utils import user_agents

@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante que cada teste inicia com pool previsível """
    monkeypatch.setattr(settings, "SCRAPER_USER_AGENT_POOL", ("UA1", "UA2", "UA3"))
    monkeypatch.setattr(settings, "SCRAPER_DEFAULT_USER_AGENT", "UA1")
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_ACCEPT", "text/html")
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_ACCEPT_LANGUAGE", "pt-BR")
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_CONNECTION", "keep-alive")
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_CACHE_CONTROL", "max-age=0")
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_ACCEPT_ENCODING", "gzip")
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_ADDITIONAL", "")
    monkeypatch.setattr(settings, "SCRAPER_HEADERS_DEFAULT_COOKIES", "")
    user_agents.reset_user_agent_state()

def test_get_user_agent_round_robin() -> None:
    """ Confirma round-robin ao distribuir User-Agent entre domínios distintos """
    collected = [
        user_agents.get_user_agent("https://primeiro.com"),
        user_agents.get_user_agent("https://segundo.com"),
        user_agents.get_user_agent("https://terceiro.com"),
        user_agents.get_user_agent("https://quarto.com"),
    ]
    assert collected == ["UA1", "UA2", "UA3", "UA1"]

def test_get_user_agent_preserva_afinidade_por_dominio() -> None:
    """ Domínios distintos devem receber valores estáveis ao longo do tempo """
    first = user_agents.get_user_agent("https://primeiro.com")
    again = user_agents.get_user_agent("primeiro.com/outro")
    seconds_domain = user_agents.get_user_agent("https://segundo.com")

    assert first == again
    assert seconds_domain != first

def test_get_user_agent_usa_padrao_quando_pool_vazio(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Quando não há pool configurado deve retornar o valor padrão """
    monkeypatch.setattr(settings, "SCRAPER_USER_AGENT_POOL", tuple())
    monkeypatch.setattr(settings, "SCRAPER_DEFAULT_USER_AGENT", "PADRAO")
    user_agents.reset_user_agent_state()

    assert user_agents.get_user_agent("https://sem-pool.com") == "PADRAO"


def test_compose_headers_retorna_campos_basicos() -> None:
    """ A composição deve incluir apenas os campos mínimos documentados """
    headers = user_agents.compose_headers("UA-TEXTO", referer="https://origem.com")

    assert headers == {
        "User-Agent": "UA-TEXTO",
        "Accept": "text/html",
        "Accept-Language": "pt-BR",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
        "Accept-Encoding": "gzip",
        "Referer": "https://origem.com",
    }

def test_compose_headers_respeita_headers_adicionais(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante que headers extras possam sobrescrever valores padrão."""

    monkeypatch.setattr(
        settings,
        "SCRAPER_HEADERS_ADDITIONAL",
        "Accept=application/json||X-Feature=ativo",
    )

    headers = user_agents.compose_headers("UA-TEXTO")

    assert headers["Accept"] == "application/json"
    assert headers["X-Feature"] == "ativo"
    