from __future__ import annotations

from importlib import import_module

import pytest

from market_scraper.utils import robots


class _FakeRedis:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}
        self.set_calls: list[tuple[str, int, str]] = []

    def get(self, key: str):
        return self.storage.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.storage[key] = value
        self.set_calls.append((key, ttl, value))


@pytest.mark.asyncio
async def test_robots_uses_operational_redis_cache_between_calls(monkeypatch):
    fake_redis = _FakeRedis()
    download_calls = {"count": 0}
    robots_impl = import_module("market_scraper.utils.robots")

    async def fake_download_robots(robots_url: str, *, timeout: float):
        download_calls["count"] += 1
        assert robots_url == "https://example.com/robots.txt"
        assert timeout == 0.5
        return "User-agent: *\nAllow: /\n"

    monkeypatch.setattr(robots_impl, "get_redis_operational", lambda: fake_redis)
    monkeypatch.setattr(robots_impl, "_download_robots", fake_download_robots)

    first = await robots.is_allowed("https://example.com/product", timeout=0.5)
    second = await robots.is_allowed("https://example.com/product", timeout=0.5)

    assert first is True
    assert second is True
    assert download_calls["count"] == 1
    assert fake_redis.set_calls == [
        (
            "robots:example.com",
            3600,
            "User-agent: *\nAllow: /\n",
        )
    ]
