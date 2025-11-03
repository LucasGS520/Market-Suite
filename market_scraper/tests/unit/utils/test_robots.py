""" Testes unitários para o utilitário de verificação de robots.txt """

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from market_scraper.utils import robots
from shared.metrics.metrics_scraper import (
    SCRAPER_ROBOTS_CHECK_TOTAL,
    SCRAPER_HTTP_RETRIES_TOTAL,
    SCRAPER_HTTP_RETRY_BACKOFF_SECONDS,
)

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
        if self.raise_error:
            raise RuntimeError("falha em can_fetch")
        return self.allowed
    
@pytest.fixture(autouse=True)
def clear_cache() -> None:
    """ Limpa cache interno antes de cada caso de teste para garantir isolamento """
    robots._ROBOTS_CACHE.clear()

def _metric_value(metric, sample_name: str, labels: dict[str, str]) -> float:
    """Obtém o valor atual de uma métrica Prometheus filtrando por labels"""

    for collected in metric.collect():
        for sample in collected.samples:
            if sample.name == sample_name and all(
                sample.labels.get(key) == value for key, value in labels.items()
            ):
                return float(sample.value)
    return 0.0


class DummyAsyncClient:
    """Client HTTP mínimo para simular respostas de robots.txt"""

    def __init__(self, responses: Iterator[httpx.Response]) -> None:
        self._responses = responses

    async def __aenter__(self) -> "DummyAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None

    async def get(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        try:
            return next(self._responses)
        except StopIteration as exc:
            raise AssertionError("Respostas insuficientes para o teste") from exc

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
async def test_is_allowed_blocks_when_parser_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ Parser ausente deve bloquear a coleta para evitar violações """
    async def fake_get_parser(host: str, robots_url: str, *, timeout: float) -> DummyRobotParser | None:
        return None
    
    monkeypatch.setattr(robots, "_get_parser", fake_get_parser)

    error_metric = SCRAPER_ROBOTS_CHECK_TOTAL.labels(outcome="error")
    before = error_metric._value.get()  # type: ignore[attr-defined]

    assert await robots.is_allowed("https://unstable.com/p") is False

    after = error_metric._value.get()  # type: ignore[attr-defined]
    assert after == before + 1


@pytest.mark.asyncio
async def test_is_allowed_blocks_when_can_fetch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ Exceções de ``can_fetch`` devem impedir a coleta """

    async def fake_get_parser(host: str, robots_url: str, *, timeout: float) -> DummyRobotParser:
        return DummyRobotParser(allowed=True, raise_error=True)

    monkeypatch.setattr(robots, "_get_parser", fake_get_parser)

    error_metric = SCRAPER_ROBOTS_CHECK_TOTAL.labels(outcome="error")
    before = error_metric._value.get()  # type: ignore[attr-defined]

    assert await robots.is_allowed("https://erro.com/item") is False

    after = error_metric._value.get()  # type: ignore[attr-defined]
    assert after == before + 1

@pytest.mark.asyncio
async def test_download_robots_respects_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante que robots.txt é refeito após Retry-After válido"""

    robots_url = "https://example.com/robots.txt"
    responses = iter(
        [
            httpx.Response(
                429,
                headers={"Retry-After": "0.2"},
                request=httpx.Request("GET", robots_url),
            ),
            httpx.Response(
                200,
                text="User-agent: *\nDisallow:",
                request=httpx.Request("GET", robots_url),
            ),
        ]
    )

    monkeypatch.setattr(
        "market_scraper.utils.robots.httpx.AsyncClient",
        lambda **_: DummyAsyncClient(responses),
    )

    counter_before = _metric_value(
        SCRAPER_HTTP_RETRIES_TOTAL,
        "scraper_http_retries_total",
        {"target": "robots", "reason": "too_many_requests"},
    )
    histogram_before = _metric_value(
        SCRAPER_HTTP_RETRY_BACKOFF_SECONDS,
        "scraper_http_retry_backoff_seconds_sum",
        {"target": "robots", "reason": "too_many_requests"},
    )

    content = await robots._download_robots(robots_url, timeout=1.0)

    assert content == "User-agent: *\nDisallow:"

    counter_after = _metric_value(
        SCRAPER_HTTP_RETRIES_TOTAL,
        "scraper_http_retries_total",
        {"target": "robots", "reason": "too_many_requests"},
    )
    histogram_after = _metric_value(
        SCRAPER_HTTP_RETRY_BACKOFF_SECONDS,
        "scraper_http_retry_backoff_seconds_sum",
        {"target": "robots", "reason": "too_many_requests"},
    )

    assert counter_after - counter_before == pytest.approx(1.0)
    assert pytest.approx(histogram_after - histogram_before, rel=0.2) == 0.2

@pytest.mark.asyncio
async def test_download_robots_retries_on_server_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Confere retries padrão diante de erros 5xx ao buscar robots.txt"""

    robots_url = "https://example.com/robots.txt"
    monkeypatch.setattr(robots.settings, "SCRAPER_HTTP_RETRY_BACKOFF_BASE", 0.05)
    responses = iter(
        [
            httpx.Response(503, request=httpx.Request("GET", robots_url)),
            httpx.Response(
                200,
                text="User-agent: *\nAllow: /",
                request=httpx.Request("GET", robots_url),
            ),
        ]
    )

    monkeypatch.setattr(
        "market_scraper.utils.robots.httpx.AsyncClient",
        lambda **_: DummyAsyncClient(responses),
    )

    counter_before = _metric_value(
        SCRAPER_HTTP_RETRIES_TOTAL,
        "scraper_http_retries_total",
        {"target": "robots", "reason": "server_error"},
    )
    histogram_before = _metric_value(
        SCRAPER_HTTP_RETRY_BACKOFF_SECONDS,
        "scraper_http_retry_backoff_seconds_sum",
        {"target": "robots", "reason": "server_error"},
    )

    content = await robots._download_robots(robots_url, timeout=1.0)

    assert content == "User-agent: *\nAllow: /"

    counter_after = _metric_value(
        SCRAPER_HTTP_RETRIES_TOTAL,
        "scraper_http_retries_total",
        {"target": "robots", "reason": "server_error"},
    )
    histogram_after = _metric_value(
        SCRAPER_HTTP_RETRY_BACKOFF_SECONDS,
        "scraper_http_retry_backoff_seconds_sum",
        {"target": "robots", "reason": "server_error"},
    )

    assert counter_after - counter_before == pytest.approx(1.0)
    assert pytest.approx(histogram_after - histogram_before, rel=0.2) == 0.05  
