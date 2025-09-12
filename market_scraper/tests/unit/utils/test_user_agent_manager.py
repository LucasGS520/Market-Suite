import pytest

from market_scraper.utils.user_agent_manager import IntelligentUserAgentManager
from importlib import reload

def _reload_manager_and_constants(tmp_file, monkeypatch):
    """ Recarrega módulos usando ``tmp_file`` como fonte de User-Agent """
    import market_scraper.utils.constants as constants
    monkeypatch.setattr(constants, "_user_agents_file", lambda: tmp_file)
    constants.USER_AGENTS = constants._load_user_agents()
    import market_scraper.utils.user_agent_manager as uam
    reload(uam)
    return uam.IntelligentUserAgentManager

def test_user_agent_persists(monkeypatch):
    """ Garante que o mesmo agente é reutilizado enquanto não atinge o limite """
    uas = iter(["UA1"])
    monkeypatch.setattr("market_scraper.utils.user_agent_manager.random.choice", lambda lst: next(uas))
    manager = IntelligentUserAgentManager(max_requests=5, session_timeout=10)

    first = manager.get_user_agent("sess")
    second = manager.get_user_agent("sess")

    assert first == "UA1"
    assert second == first

def test_user_agent_rotates_after_max_requests(monkeypatch):
    """ Verifica a rotação após exceder o número máximo de requisições """
    uas = iter(["UA1", "UA2"])
    monkeypatch.setattr("market_scraper.utils.user_agent_manager.random.choice", lambda lst: next(uas))
    manager = IntelligentUserAgentManager(max_requests=2, session_timeout=10)

    assert manager.get_user_agent("s") == "UA1"
    assert manager.get_user_agent("s") == "UA1"
    assert manager.get_user_agent("s") == "UA2"

def test_user_agent_rotates_after_timeout(monkeypatch):
    """ Testa rotação do agente quando o tempo de sessão expira """
    uas = iter(["UA1", "UA2"])
    monkeypatch.setattr("market_scraper.utils.user_agent_manager.random.choice", lambda lst: next(uas))

    times = [0.0, 1.0, 6.0]
    monkeypatch.setattr("market_scraper.utils.user_agent_manager.time.monotonic", lambda: times.pop(0))

    manager = IntelligentUserAgentManager(max_requests=5, session_timeout=5)

    assert manager.get_user_agent("t") == "UA1"
    assert manager.get_user_agent("t") == "UA1"
    assert manager.get_user_agent("t") == "UA2"

def test_dynamic_user_agent_loading(tmp_path, monkeypatch):
    """ Garante que a lista é carregada do arquivo externo quando disponível """
    file = tmp_path / "user_agents.txt"
    file.write_text("UA_FILE\n", encoding="utf-8")

    Manager = _reload_manager_and_constants(file, monkeypatch)
    manager = Manager()
    assert manager.get_user_agent("sess") == "UA_FILE"
