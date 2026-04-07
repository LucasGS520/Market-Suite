""" Testes unitarios para identidade de cliente e protecoes de brute force. """

from __future__ import annotations

import pytest
from fastapi import HTTPException, status

from market_alert.infrastructure.security import bruteforce, client_identity


pytestmark = pytest.mark.unit


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.expirations: list[tuple[str, int]] = []
        self.deleted: list[str] = []

    def get(self, key: str):
        return self.values.get(key)

    def incr(self, key: str) -> int:
        self.values[key] = int(self.values.get(key, 0)) + 1
        return self.values[key]

    def expire(self, key: str, ttl: int) -> None:
        self.expirations.append((key, ttl))

    def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)


def test_resolve_client_ip_prefers_x_real_ip(build_request) -> None:
    request = build_request(
        headers={
            "x-real-ip": "198.51.100.1",
            "x-forwarded-for": "198.51.100.2, 198.51.100.3",
        },
        client=("198.51.100.4", 9000),
    )

    assert client_identity.resolve_client_ip(request) == "198.51.100.1"


def test_resolve_client_ip_uses_first_forwarded_for(build_request) -> None:
    request = build_request(
        headers={"x-forwarded-for": "198.51.100.2, 198.51.100.3"},
        client=("198.51.100.4", 9000),
    )

    assert client_identity.resolve_client_ip(request) == "198.51.100.2"


def test_block_ip_raises_when_ip_account_threshold_is_reached(monkeypatch, build_request) -> None:
    fake_redis = FakeRedis()
    request = build_request(client=("203.0.113.10", 8080))
    login_key = bruteforce._login_key("203.0.113.10", "user@example.com")
    fake_redis.values[login_key] = bruteforce.settings.BRUTE_FORCE_MAX_ATTEMPTS

    monkeypatch.setattr(bruteforce, "redis_client", fake_redis)
    monkeypatch.setattr(bruteforce, "resolve_client_ip", lambda request: "203.0.113.10")

    with pytest.raises(HTTPException) as exc_info:
        bruteforce.block_ip(request, identifier="user@example.com", fingerprint="fp-1")

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_record_failed_attempt_tracks_all_counters_and_ttls(monkeypatch, build_request) -> None:
    fake_redis = FakeRedis()
    request = build_request(client=("203.0.113.10", 8080))

    monkeypatch.setattr(bruteforce, "redis_client", fake_redis)
    monkeypatch.setattr(bruteforce, "resolve_client_ip", lambda request: "203.0.113.10")

    bruteforce.record_failed_attempt(
        request,
        identifier="user@example.com",
        fingerprint="fp-1",
    )

    assert fake_redis.values[bruteforce._login_key("203.0.113.10", "user@example.com")] == 1
    assert fake_redis.values[bruteforce._account_key("user@example.com")] == 1
    assert fake_redis.values[bruteforce._device_key("fp-1")] == 1
    assert len(fake_redis.expirations) == 3


def test_reset_failed_attempts_deletes_all_counter_keys(monkeypatch, build_request) -> None:
    fake_redis = FakeRedis()
    request = build_request(client=("203.0.113.10", 8080))

    monkeypatch.setattr(bruteforce, "redis_client", fake_redis)
    monkeypatch.setattr(bruteforce, "resolve_client_ip", lambda request: "203.0.113.10")

    bruteforce.reset_failed_attempts(
        request,
        identifier="user@example.com",
        fingerprint="fp-1",
    )

    assert bruteforce._login_key("203.0.113.10", "user@example.com") in fake_redis.deleted
    assert bruteforce._account_key("user@example.com") in fake_redis.deleted
    assert bruteforce._device_key("fp-1") in fake_redis.deleted


def test_enforce_rate_limit_raises_after_limit(monkeypatch) -> None:
    fake_redis = FakeRedis()
    fake_redis.values["rate:test"] = 2

    monkeypatch.setattr(bruteforce, "redis_client", fake_redis)

    with pytest.raises(HTTPException) as exc_info:
        bruteforce.enforce_rate_limit(
            key="rate:test",
            max_attempts=2,
            window_seconds=60,
            error_message="slow down",
        )

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
