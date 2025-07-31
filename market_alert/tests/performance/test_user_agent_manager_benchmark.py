import random

from app.utils.user_agent_manager import IntelligentUserAgentManager


def test_user_agent_rotation_performance(benchmark, monkeypatch):
    monkeypatch.setattr(random, "choice", lambda lst: lst[0])
    manager = IntelligentUserAgentManager(max_requests=1, session_timeout=100)
    benchmark(manager.get_user_agent, "sess")
