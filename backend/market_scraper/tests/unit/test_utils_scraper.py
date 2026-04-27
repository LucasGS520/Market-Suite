from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx

from shared.schemas import ParserResponse

from market_scraper.infra.cache import conditional_payload as conditional_payload_module
from market_scraper.utils import http_utils as http_utils_module
from market_scraper.utils import robots as robots_module
from market_scraper.infra.cache.conditional_payload import (
    build_cache_headers,
    get_cached_response,
    match_if_none_match,
    parse_if_modified_since,
    should_return_not_modified,
    store_response,
)
from market_scraper.utils.http_utils import HostResolutionError, parse_retry_after
from market_scraper.utils.price import format_decimal_to_str, parse_price_str


def test_conditional_payload_roundtrip_and_headers(monkeypatch):
    stored = {}

    monkeypatch.setattr(
        conditional_payload_module.cache,
        "set",
        lambda key, value, ttl: stored.setdefault(key, value),
    )
    monkeypatch.setattr(
        conditional_payload_module.cache,
        "get",
        lambda key: stored.get(key),
    )
    monkeypatch.setattr(
        conditional_payload_module.cache,
        "invalidate",
        lambda key: stored.pop(key, None),
    )

    response = ParserResponse(
        name="Produto",
        current_price=Decimal("12.34"),
        url="https://example.com/product",
        source="example.com",
    )

    metadata = store_response("https://example.com/product", response)
    cached = get_cached_response("https://example.com/product")
    headers = build_cache_headers(metadata)

    assert cached is not None
    assert cached.etag == metadata.etag
    assert cached.payload.name == "Produto"
    assert headers["ETag"] == f'"{metadata.etag}"'
    assert headers["Cache-Control"] == "max-age=0, must-revalidate"


def test_conditional_helpers_match_etag_and_modified_since():
    metadata = conditional_payload_module.CachedResponseMetadata(
        etag="abc123",
        last_modified=datetime.now(timezone.utc).replace(microsecond=0),
        payload=ParserResponse(
            name="Produto",
            url="https://example.com/product",
            source="example.com",
        ),
    )
    newer = metadata.last_modified + timedelta(seconds=10)

    assert match_if_none_match('"abc123"', "abc123") is True
    assert parse_if_modified_since("invalid-date") is None
    assert should_return_not_modified(
        if_none_match=None,
        if_modified_since=newer,
        metadata=metadata,
    ) is True


def test_parse_price_str_and_format_decimal_cover_common_inputs():
    assert parse_price_str("R$ 1.234,56", "https://example.com") == Decimal("1234.56")
    assert parse_price_str(10, "https://example.com") == Decimal("10")
    assert format_decimal_to_str(Decimal("9.5")) == "9.50"


def test_parse_retry_after_accepts_seconds_and_http_date():
    future = datetime.now(timezone.utc) + timedelta(seconds=5)

    assert parse_retry_after("1.5") == 1.5
    assert parse_retry_after(future.strftime("%a, %d %b %Y %H:%M:%S GMT")) is not None
    assert parse_retry_after("not-a-date") is None


def test_resolve_public_address_uses_cache_and_blocks_private(monkeypatch):
    http_utils_module._DNS_CACHE.clear()
    calls = {"count": 0}

    def fake_resolve(host: str) -> list[str]:
        calls["count"] += 1
        return ["8.8.8.8", "8.8.8.8"]

    monkeypatch.setattr(http_utils_module, "_resolve_host_records", fake_resolve)
    monkeypatch.setattr(http_utils_module.settings, "SCRAPER_DNS_CACHE_TTL", 10.0)

    first = http_utils_module.resolve_public_address("example.com")
    second = http_utils_module.resolve_public_address("example.com")

    assert first == ["8.8.8.8"]
    assert second == ["8.8.8.8"]
    assert calls["count"] == 1

    monkeypatch.setattr(
        http_utils_module,
        "_resolve_host_records",
        lambda host: ["127.0.0.1"],
    )
    http_utils_module._DNS_CACHE.clear()
    try:
        http_utils_module.resolve_public_address("localhost")
    except HostResolutionError as exc:
        assert "bloqueado" in str(exc)
    else:
        raise AssertionError("Era esperado bloquear IP nao publico")


def test_robots_retryable_response_reads_retry_after():
    request = httpx.Request("GET", "https://example.com/product")
    response = httpx.Response(
        429,
        request=request,
        headers={"Retry-After": "2"},
    )

    try:
        robots_module._raise_for_retryable_robots_response(response)
    except robots_module._RetryableRobotsHTTPError as exc:
        assert exc.reason == "too_many_requests"
        assert exc.retry_after == 2.0
    else:
        raise AssertionError("Era esperado levantar _RetryableRobotsHTTPError")


async def test_robots_retrying_operation_retries_request_error(monkeypatch):
    monkeypatch.setattr(robots_module.settings, "SCRAPER_HTTP_RETRIES", 1)
    monkeypatch.setattr(robots_module.settings, "SCRAPER_HTTP_RETRY_BACKOFF_BASE", 0.0)

    attempts = {"count": 0}

    async def flaky_operation() -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            request = httpx.Request("GET", "https://example.com/product")
            raise httpx.RequestError("network", request=request)
        return httpx.Response(
            200,
            request=httpx.Request("GET", "https://example.com/product"),
        )

    wrapped = robots_module._build_robots_retrying_operation(flaky_operation)

    response = await wrapped()

    assert response.status_code == 200
    assert attempts["count"] == 2
