""" Testes unitários para o utilitário de verificação de robots.txt """

from __future__ import annotations

import pytest

from market_scraper.utils import robots
from shared.metrics.metrics_scraper import SCRAPER_ROBOTS_CHECK_TOTAL


class DummyRobotParser:
    """ Simula comportamento do ``RobotFileParser`` para cenários controlados """
    def __init__(self, allowed: bool = True, raise_error: bool = False) -> None:
        self.allowed = allowed
        self.raise_error = raise_error
        self.robots_url: str | None = None

    def set_url(self, robots_url: str) -> None:
        self.robots_url = robots_url

    def parse(self, _: list[str]) -> None:
        if self.raise_error:
            raise RuntimeError("falha ao obter robots.txt")
        
    def can_fetch(self, user_agent: str, url: str) -> bool:
        return self.allowed
    
@pytest.fixture(autouse=True)
def clear_cache() -> None:
    """ Limpa cache interno antes de cada caso de teste para garantir isolamento """
    robots._ROBOTS_CACHE.clear()

@pytest.mark.asyncio
async def test_is_allowed_returns_true_when_robot_permits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ Valida que URLs liberadas incrementam a métrica corretamente """
    async def fake_get_parser(host: str, robots_url: str, *, timeout: float) -> DummyRobotParser:
        return DummyRobotParser(allowed=True)

    monkeypatch.setattr(robots, "_get_parser", fake_get_parser)
    allowed_metric = SCRAPER_ROBOTS_CHECK_TOTAL.labels(outcome="allowed")
    before = allowed_metric._value.get()  # type: ignore[attr-defined]

    assert await robots.is_allowed("https://example.com/produto") is True

    after = allowed_metric._value.get()  # type: ignore[attr-defined]
    assert after == before + 1

@pytest.mark.asyncio
async def test_is_allowed_returns_false_when_robot_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ Assegura que bloqueios de robots.txt são propagados e metrificados """
    async def fake_get_parser(host: str, robots_url: str, *, timeout: float) -> DummyRobotParser:
        return DummyRobotParser(allowed=False)
    
    monkeypatch.setattr(robots, "_get_parser", fake_get_parser)
    disallowed_metric = SCRAPER_ROBOTS_CHECK_TOTAL.labels(outcome="disallowed")
    before = disallowed_metric._value.get()  # type: ignore[attr-defined]

    assert await robots.is_allowed("https://blocked.com/item") is False

    after = disallowed_metric._value.get()  # type: ignore[attr-defined]
    assert after == before + 1


@pytest.mark.asyncio
async def test_is_allowed_defaults_to_true_on_fetch_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ Confere fallback permissivo quando ocorrer falha ao baixar robots.txt """
    async def fake_get_parser(host: str, robots_url: str, *, timeout: float) -> DummyRobotParser | None:
        return None
    
    monkeypatch.setattr(robots, "_get_parser", fake_get_parser)
    error_metric = SCRAPER_ROBOTS_CHECK_TOTAL.labels(outcome="error")
    before = error_metric._value.get()  # type: ignore[attr-defined]

    assert await robots.is_allowed("https://unstable.com/p") is True

    after = error_metric._value.get()  # type: ignore[attr-defined]
    assert after == before + 1
