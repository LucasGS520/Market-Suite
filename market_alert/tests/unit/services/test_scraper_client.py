""" Testes unitários para o cliente HTTP do scraper """

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from types import SimpleNamespace

import httpx
import pytest

from market_alert.scraper.scraper_client import (
    ScraperClient,
    ScraperClientError,
    ScraperFetchResult,
)


class _DummyAsyncClient:
    """ Cliente HTTP falso que devolve respostas pré-configuradas """
    def __init__(self, responses: list[httpx.Response]):
        self._responses = responses
        self.calls = 0

    async def post(self, url: str, json: dict[str, str], headers: dict[str, str] | None = None) -> httpx.Response:
        response = self._responses[self.calls]
        self.calls += 1
        return response

    async def aclose(self) -> None:
        return None
    
@pytest.fixture(autouse=True)
def _patch_protections(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Desativa rate limiter e circuit breaker para os testes """
    
    monkeypatch.setattr("market_alert.scraper.scraper_client.rate_limiter.allow", lambda host: True)
    monkeypatch.setattr("market_alert.scraper.scraper_client.circuit_breaker.is_open", lambda host: False)
    monkeypatch.setattr("market_alert.scraper.scraper_client.circuit_breaker.record_success", lambda host: None)
    monkeypatch.setattr("market_alert.scraper.scraper_client.circuit_breaker.record_failure", lambda host: None)

def _build_response(status: int, json_payload: dict | None = None, headers: dict[str, str] | None = None) -> httpx.Response:
    """ Ajuda a construir ``httpx.Response`` com request associado """
    request = httpx.Request("POST", "http://fake/scraper/parse")
    return httpx.Response(
        status,
        json=json_payload,
        headers=headers or {},
        request=request,
    )

@pytest.mark.asyncio
async def test_fetch_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Quando o scraper responde 200 o payload deve ser retornado """
    responses = [_build_response(200, {"name": "A", "current_price": 10, "url": "http://a", "source": "test"})]
    monkeypatch.setattr("market_alert.scraper.scraper_client.httpx.AsyncClient", lambda *a, **k: _DummyAsyncClient(responses))

    client = ScraperClient(base_url="http://fake")
    result = await client.fetch(url="http://produto", monitored_id=None)
    assert isinstance(result, ScraperFetchResult)
    assert result.status_code == 200
    assert result.payload is not None
    assert result.payload.name == "A"
    await client.aclose()

@pytest.mark.asyncio
async def test_fetch_returns_not_modified(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Status 304 deve retornar resultado sem payload """

    responses = [_build_response(304, None, {"ETag": "abc"})]
    monkeypatch.setattr("market_alert.scraper.scraper_client.httpx.AsyncClient", lambda *a, **k: _DummyAsyncClient(responses))

    client = ScraperClient(base_url="http://fake")
    result = await client.fetch(url="http://produto", monitored_id=None, etag="abc")
    assert result.status_code == 304
    assert result.payload is None
    await client.aclose()

@pytest.mark.asyncio
async def test_fetch_handles_no_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Resposta 422 com ``no_result`` deve ser devolvida ao chamador """

    responses = [_build_response(422, {"error_code": "no_result"})]
    monkeypatch.setattr("market_alert.scraper.scraper_client.httpx.AsyncClient", lambda *a, **k: _DummyAsyncClient(responses))

    client = ScraperClient(base_url="http://fake")
    result = await client.fetch(url="http://produto", monitored_id=None)
    assert result.status_code == 422
    assert result.error_code == "no_result"
    await client.aclose()

@pytest.mark.asyncio
async def test_fetch_raises_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Após exceder tentativas em erro 5xx o cliente levanta exceção."""

    responses = [_build_response(500), _build_response(500), _build_response(500)]
    monkeypatch.setattr("market_alert.scraper.scraper_client.httpx.AsyncClient", lambda *a, **k: _DummyAsyncClient(responses))

    async def _fake_sleep(*_: object) -> None:
        return None

    monkeypatch.setattr("market_alert.scraper.scraper_client.asyncio.sleep", _fake_sleep)
    monkeypatch.setattr("market_alert.scraper.scraper_client.settings", SimpleNamespace(
        SCRAPER_TOTAL_TIMEOUT=8.0,
        SCRAPER_CONNECT_TIMEOUT=5.0,
        SCRAPER_READ_TIMEOUT=5.0,
        SCRAPER_RETRY_ATTEMPTS=2,
        SCRAPER_RETRY_BACKOFF_MIN=0.1,
        SCRAPER_RETRY_BACKOFF_MAX=0.2,
        SCRAPER_HOST_RATE_LIMIT=10,
        SCRAPER_HOST_RATE_WINDOW_SECONDS=60,
        SCRAPER_CIRCUIT_FAILURE_THRESHOLD=5,
        SCRAPER_CIRCUIT_WINDOW_SECONDS=600,
        SCRAPER_CIRCUIT_COOLDOWN_SECONDS=600,
        SCRAPER_SERVICE_URL="http://fake",
        SCRAPER_SERVICE_AUTH_HEADER=None,
        SCRAPER_SERVICE_AUTH_TOKEN=None,
    ))

    client = ScraperClient(base_url="http://fake")
    with pytest.raises(ScraperClientError) as exc:
        await client.fetch(url="http://produto", monitored_id=None)
    assert exc.value.status_code == 500
    await client.aclose()

@pytest.mark.asyncio
async def test_fetch_uses_retry_after_header_with_http_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Confere se cabeçalho ``Retry-After`` em formato HTTP-date é respeitado """
    future = datetime.now(timezone.utc) + timedelta(seconds=7)
    header_value = format_datetime(future, usegmt=True)

    responses = [
        _build_response(429, headers={"Retry-After": header_value}),
        _build_response(200, {"name": "A", "current_price": 10, "url": "http://a", "source": "test"}),
    ]

    monkeypatch.setattr("market_alert.scraper.scraper_client.httpx.AsyncClient", lambda *a, **k: _DummyAsyncClient(responses))

    sleep_calls: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr("market_alert.scraper.scraper_client.asyncio.sleep", _fake_sleep)
    monkeypatch.setattr("market_alert.scraper.scraper_client.settings", SimpleNamespace(
        SCRAPER_TOTAL_TIMEOUT=8.0,
        SCRAPER_CONNECT_TIMEOUT=5.0,
        SCRAPER_READ_TIMEOUT=5.0,
        SCRAPER_RETRY_ATTEMPTS=2,
        SCRAPER_RETRY_BACKOFF_MIN=30.0,
        SCRAPER_RETRY_BACKOFF_MAX=60.0,
        SCRAPER_HOST_RATE_LIMIT=10,
        SCRAPER_HOST_RATE_WINDOW_SECONDS=60,
        SCRAPER_CIRCUIT_FAILURE_THRESHOLD=5,
        SCRAPER_CIRCUIT_WINDOW_SECONDS=600,
        SCRAPER_CIRCUIT_COOLDOWN_SECONDS=600,
        SCRAPER_SERVICE_URL="http://fake",
        SCRAPER_SERVICE_AUTH_HEADER=None,
        SCRAPER_SERVICE_AUTH_TOKEN=None,
    ))

    client = ScraperClient(base_url="http://fake")
    result = await client.fetch(url="http://produto", monitored_id=None)
    await client.aclose()

    assert result.status_code == 200
    assert sleep_calls, "esperava chamada de retry baseada no cabeçalho"
    assert 5 <= sleep_calls[0] <= 7
    
