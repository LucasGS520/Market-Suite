from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import brotli
import httpx
import pytest

from market_scraper.utils.http_utils import (
    ContentDecodeError,
    HostResolutionError,
    _DNS_CACHE,
    decode_http_body,
    resolve_public_address,
    parse_retry_after,
)
from shared.metrics.metrics_scraper import SCRAPER_DNS_BLOCKED_TOTAL

class DummyResponse:
    """ Resposta sintética para exercitar caminhos de decodificação manual """
    def __init__(self, content: bytes, headers: dict[str, str] | None = None) -> None:
        self._content = content
        self.headers = headers or {}
        self.encoding: str | None = None
        self.charset: str | None = None
        self.request = httpx.Request("GET", "https://example.com")

    @property
    def text(self) -> str:
        raise httpx.DecodingError("erro", request=self.request)
    
    @property
    def content(self) -> bytes:
        return self._content

def test_parse_retry_after_seconds():
    assert parse_retry_after("30") == pytest.approx(30.0)

def test_parse_retry_after_fractional_seconds():
    assert parse_retry_after("1.5") == pytest.approx(1.5)

def test_parse_retry_after_http_date():
    future = datetime.now(timezone.utc) + timedelta(seconds=20)
    header = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
    result = parse_retry_after(header)
    assert result is not None
    assert 0.0 <= result <= 20.0

def test_resolve_public_address_blocks_private_ip(monkeypatch):
    _DNS_CACHE.clear()
    blocked_metric = SCRAPER_DNS_BLOCKED_TOTAL.labels(reason="non_public")._value.get()

    monkeypatch.setattr(
        "market_scraper.utils.http_utils._resolve_host_records",
        lambda host: ["10.0.0.1"],
    )

    with pytest.raises(HostResolutionError):
        resolve_public_address("intranet.local")

    new_metric = SCRAPER_DNS_BLOCKED_TOTAL.labels(reason="non_public")._value.get()
    assert new_metric == blocked_metric + 1

def test_resolve_public_address_timeout(monkeypatch):
    _DNS_CACHE.clear()

    def _raise_timeout(host: str) -> list[str]:
        raise HostResolutionError("Timeout simulado")
    
    monkeypatch.setattr(
        "market_scraper.utils.http_utils._resolve_host_records",
        _raise_timeout,
    )

    with pytest.raises(HostResolutionError):
        resolve_public_address("example.com")

def test_resolve_public_address_uses_cache(monkeypatch):
    _DNS_CACHE.clear()

    from market_scraper.utils import http_utils

    fake_settings = SimpleNamespace(
        SCRAPER_DNS_CACHE_TTL=60,
        SCRAPER_DNS_TIMEOUT=getattr(http_utils.settings, "SCRAPER_DNS_TIMEOUT", 2.0),
    )
    monkeypatch.setattr(http_utils, "settings", fake_settings)

    calls: list[str] = []

    def _fake_resolver(host: str) -> list[str]:
        calls.append(host)
        return ["8.8.8.8"]
    
    monkeypatch.setattr(
        "market_scraper.utils.http_utils._resolve_host_records",
        _fake_resolver,
    )

    first = resolve_public_address("example.com")
    second = resolve_public_address("example.com")

    assert first == ["8.8.8.8"]
    assert second == ["8.8.8.8"]
    assert calls == ["example.com"]

def test_decode_http_body_handles_brotli() -> None:
    """ Garante decodificação Brotli quando a resposta vem compactada """
    original = "<html>brotli</html>"
    response = DummyResponse(
        brotli.compress(original.encode("utf-8")),
        headers={"Content-Encoding": "br"},
    )

    decoded = decode_http_body(response)

    assert decoded == original

def test_decode_http_body_handles_gzip() -> None:
    """ Confere suporte á decodificação gzip utilizando fallback interno """
    import gzip
    import io

    original = "<html>gzip</html>"
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as gz_file:
        gz_file.write(original.encode("utf-8"))
    response = DummyResponse(
        buffer.getvalue(),
        headers={"Content-Encoding": "gzip"},
    )

    decoded = decode_http_body(response)

    assert decoded == original

def test_decode_http_body_raises_on_invalid_payload() -> None:
    """ Verifica se a função sinaliza erros de decodificação em payload inválido """
    response = DummyResponse(b"\x00\x01", headers={"Content-Encoding": "gzip"})

    with pytest.raises(ContentDecodeError):
        decode_http_body(response)
    