""" Testes unitários para o cliente HTTP do scraper """

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from types import SimpleNamespace
from uuid import UUID
from unittest.mock import Mock

import httpx
import pytest

from market_alert.scraper.scraper_client import (
    ScraperClient,
    ScraperClientError,
    ScraperFetchResult,
    _build_timeout,
)


class _DummyClient:
    """ Cliente HTTP falso que devolve respostas pré-configuradas """
    def __init__(self, responses: list[httpx.Response]):
        self._responses = responses
        self.calls = 0
        self.sent_headers: list[dict[str, str]] = []

    def post(
        self,
        url: str,
        json: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        self.sent_headers.append(dict(headers or {}))
        response = self._responses[self.calls]
        self.calls += 1
        return response

    def close(self) -> None:
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

def test_fetch_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Quando o scraper responde 200 o payload deve ser retornado """
    responses = [_build_response(200, {"name": "A", "current_price": 10, "url": "http://a", "source": "test"})]
    monkeypatch.setattr("market_alert.scraper.scraper_client.httpx.Client", lambda *a, **k: _DummyClient(responses))

    client = ScraperClient(base_url="http://fake")
    result = client.fetch(url="http://produto", monitored_id=None)
    assert isinstance(result, ScraperFetchResult)
    assert result.status_code == 200
    assert result.payload is not None
    assert result.payload.name == "A"
    client.close()

def test_fetch_returns_not_modified(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Status 304 deve retornar resultado sem payload """

    responses = [_build_response(304, None, {"ETag": "abc"})]
    monkeypatch.setattr("market_alert.scraper.scraper_client.httpx.Client", lambda *a, **k: _DummyClient(responses))


    client = ScraperClient(base_url="http://fake")
    result = client.fetch(url="http://produto", monitored_id=None, etag="abc")
    assert result.status_code == 304
    assert result.payload is None
    client.close()

def test_fetch_does_not_leak_conditional_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ Garante que cabeçalhos condicionais não vazem entre chamadas consecutivas """

    responses = [
        _build_response(304, None, {"ETag": "servidor-etag"}),
        _build_response(
            200,
            {"name": "Produto", "current_price": 10.0, "url": "http://a", "source": "test"},
        ),
    ]

    dummy_client = _DummyClient(responses)
    monkeypatch.setattr(
        "market_alert.scraper.scraper_client.httpx.Client",
        lambda *a, **k: dummy_client,
    )

    client = ScraperClient(base_url="http://fake")
    client.fetch(url="http://produto", monitored_id=None, etag="abc")
    client.fetch(url="http://produto", monitored_id=None)
    client.close()

    assert dummy_client.sent_headers[0].get("If-None-Match") == "abc"
    assert "If-None-Match" not in dummy_client.sent_headers[1]
    assert "If-Modified-Since" not in dummy_client.sent_headers[1]

def test_parse_returns_none_on_not_modified(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parse deve retornar ``None`` quando o scraper responder 304"""
    fetch_mock = Mock(
        return_value=ScraperFetchResult(status_code=304, payload=None, headers={})
    )
    monkeypatch.setattr(ScraperClient, "fetch", fetch_mock)

    client = ScraperClient(base_url="http://fake")
    resultado = client.parse(
        url="http://produto",
        etag="abc",
        last_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
        force_refresh=False,
    )
    client.close()

    fetch_mock.assert_called_once()
    assert resultado is None

def test_parse_forwards_conditional_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Confere se parâmetros condicionais são repassados para ``fetch``"""

    fetch_mock = Mock(
        return_value=ScraperFetchResult(status_code=304, payload=None, headers={})
    )
    monkeypatch.setattr(ScraperClient, "fetch", fetch_mock)

    client = ScraperClient(base_url="http://fake")
    last_modified = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
    client.parse(
        url="http://produto",
        monitored_id="mid",
        product_type="monitored",
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        metadata={"a": "b"},
        etag="xyz",
        last_modified=last_modified,
        force_refresh=True,
    )
    client.close()

    args = fetch_mock.call_args
    assert args is not None
    assert args.kwargs["etag"] == "xyz"
    assert args.kwargs["last_modified"] == last_modified
    assert args.kwargs["force_refresh"] is True

def test_fetch_handles_no_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Resposta 422 com ``no_result`` deve ser devolvida ao chamador """

    responses = [_build_response(422, {"error_code": "no_result"})]
    monkeypatch.setattr("market_alert.scraper.scraper_client.httpx.Client", lambda *a, **k: _DummyClient(responses))

    client = ScraperClient(base_url="http://fake")
    result = client.fetch(url="http://produto", monitored_id=None)
    assert result.status_code == 422
    assert result.error_code == "no_result"
    client.close()

def test_fetch_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Deve falhar quando o serviço retorna JSON malformado """
    request = httpx.Request("POST", "http://fake/scraper/parse")
    responses = [httpx.Response(200, content=b"not-json", request=request)]
    monkeypatch.setattr(
        "market_alert.scraper.scraper_client.httpx.Client",
        lambda *a, **k: _DummyClient(responses),
    )

    client = ScraperClient(base_url="http://fake")

    with pytest.raises(ScraperClientError) as exc:
        client.fetch(url="http://produto", monitored_id=None)

    assert exc.value.status_code == 500
    client.close()

def test_fetch_raises_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Após exceder tentativas em erro 5xx o cliente levanta exceção."""

    responses = [_build_response(500), _build_response(500), _build_response(500)]
    monkeypatch.setattr("market_alert.scraper.scraper_client.httpx.Client", lambda *a, **k: _DummyClient(responses))

    def _fake_sleep(*_: object) -> None:
        return None

    monkeypatch.setattr("market_alert.scraper.scraper_client.time.sleep", _fake_sleep)
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
        client.fetch(url="http://produto", monitored_id=None)
    assert exc.value.status_code == 500
    client.close()

def test_build_timeout_adjusts_total(monkeypatch: pytest.MonkeyPatch) -> None:
    """Timeout total deve respeitar mínimo coerente com connect + read"""

    monkeypatch.setattr(
        "market_alert.scraper.scraper_client.settings",
        SimpleNamespace(
            SCRAPER_TOTAL_TIMEOUT=5.0,
            SCRAPER_CONNECT_TIMEOUT=3.0,
            SCRAPER_READ_TIMEOUT=4.0,
        ),
    )

    timeout = _build_timeout()

    assert timeout.read == 4.0
    assert timeout.connect == 3.0
    assert timeout.pool == pytest.approx(7.0)

def test_fetch_uses_retry_after_header_with_http_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Confere se cabeçalho ``Retry-After`` em formato HTTP-date é respeitado """
    future = datetime.now(timezone.utc) + timedelta(seconds=7)
    header_value = format_datetime(future, usegmt=True)

    responses = [
        _build_response(429, headers={"Retry-After": header_value}),
        _build_response(200, {"name": "A", "current_price": 10, "url": "http://a", "source": "test"}),
    ]

    monkeypatch.setattr("market_alert.scraper.scraper_client.httpx.Client", lambda *a, **k: _DummyClient(responses))

    sleep_calls: list[float] = []

    def _fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr("market_alert.scraper.scraper_client.time.sleep", _fake_sleep)
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
    result = client.fetch(url="http://produto", monitored_id=None)
    client.close()

    assert result.status_code == 200
    assert sleep_calls, "esperava chamada de retry baseada no cabeçalho"
    assert 5 <= sleep_calls[0] <= 7
