import pytest

from app.utils.user_agent_manager import IntelligentUserAgentManager

def test_user_agent_persists(monkeypatch):
    """ Garante que o mesmo agente é reutilizado enquanto não atinge o limite """
    uas = iter(["UA1"])
    monkeypatch.setattr("app.utils.user_agent_manager.random.choice", lambda lst: next(uas))
    manager = IntelligentUserAgentManager(max_requests=5, session_timeout=10)

    first = manager.get_user_agent("sess")
    second = manager.get_user_agent("sess")

    assert first == "UA1"
    assert second == first

def test_user_agent_rotates_after_max_requests(monkeypatch):
    """ Verifica a rotação após exceder o número máximo de requisições """
    uas = iter(["UA1", "UA2"])
    monkeypatch.setattr("app.utils.user_agent_manager.random.choice", lambda lst: next(uas))
    manager = IntelligentUserAgentManager(max_requests=2, session_timeout=10)

    assert manager.get_user_agent("s") == "UA1"
    assert manager.get_user_agent("s") == "UA1"
    assert manager.get_user_agent("s") == "UA2"

def test_user_agent_rotates_after_timeout(monkeypatch):
    """ Testa rotação do agente quando o tempo de sessão expira """
    uas = iter(["UA1", "UA2"])
    monkeypatch.setattr("app.utils.user_agent_manager.random.choice", lambda lst: next(uas))

    times = [0.0, 1.0, 6.0]
    monkeypatch.setattr("app.utils.user_agent_manager.time.monotonic", lambda: times.pop(0))

    manager = IntelligentUserAgentManager(max_requests=5, session_timeout=5)

    assert manager.get_user_agent("t") == "UA1"
    assert manager.get_user_agent("t") == "UA1"
    assert manager.get_user_agent("t") == "UA2"
