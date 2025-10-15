from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from market_scraper.utils.http_utils import (
    HostResolutionError,
    _DNS_CACHE,
    resolve_public_address,
    parse_retry_after,
)
from shared.metrics.metrics_scraper import SCRAPER_DNS_BLOCKED_TOTAL

def test_parse_retry_after_seconds():
    assert parse_retry_after("30") == 30

def test_parse_retry_after_http_date():
    future = datetime.now(timezone.utc) + timedelta(seconds=20)
    header = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
    result = parse_retry_after(header)
    assert 0 < result <= 20

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
    