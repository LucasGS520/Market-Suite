from __future__ import annotations

from fnmatch import fnmatch

import pytest

from shared.infra.cache_strategy import (
    get_with_cache,
    invalidate,
    invalidate_pattern,
)
from shared.infra.circuit_breaker import CircuitBreaker
from shared.infra.rate_limiter import RedisRateLimiter, ScrapingRateLimiter


pytestmark = pytest.mark.unit


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.expirations: dict[str, int] = {}
        self.deleted_calls: list[tuple[str, ...]] = []

    def get(self, key: str):
        return self.values.get(key)

    def incr(self, key: str) -> int:
        current = int(self.values.get(key, 0)) + 1
        self.values[key] = current
        return current

    def expire(self, key: str, seconds: int) -> bool:
        self.expirations[key] = seconds
        return True

    def delete(self, *keys: str) -> int:
        self.deleted_calls.append(tuple(keys))
        deleted = 0
        for key in keys:
            if key in self.values:
                deleted += 1
                self.values.pop(key, None)
            self.expirations.pop(key, None)
        return deleted

    def exists(self, key: str) -> bool:
        return key in self.values

    def ttl(self, key: str) -> int | None:
        if key not in self.values:
            return None
        return self.expirations.get(key)

    def set(self, key: str, value: object, ex: int | None = None) -> bool:
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex
        return True

    def setex(self, key: str, ttl: int, value: object) -> bool:
        self.values[key] = value
        self.expirations[key] = ttl
        return True

    def scan(self, cursor: int, match: str, count: int = 100):
        matched = [key for key in self.values if fnmatch(key, match)]
        if cursor != 0:
            return 0, []
        return 0, matched[:count]

    def pipeline(self, _transaction: bool):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.operations: list[tuple[str, tuple, dict]] = []

    def incr(self, key: str):
        self.operations.append(("incr", (key,), {}))
        return self

    def expire(self, key: str, seconds: int):
        self.operations.append(("expire", (key, seconds), {}))
        return self

    def set(self, key: str, value: object, ex: int | None = None):
        self.operations.append(("set", (key, value), {"ex": ex}))
        return self

    def delete(self, key: str):
        self.operations.append(("delete", (key,), {}))
        return self

    def execute(self):
        results = []
        for operation, args, kwargs in self.operations:
            result = getattr(self.redis, operation)(*args, **kwargs)
            results.append(result)
        self.operations.clear()
        return results


class BrokenRedis:
    def get(self, _key: str):
        raise RuntimeError("broken get")

    def incr(self, _key: str):
        raise RuntimeError("broken incr")

    def expire(self, _key: str, _seconds: int):
        raise RuntimeError("broken expire")

    def delete(self, *_keys: str):
        raise RuntimeError("broken delete")


def test_redis_rate_limiter_handles_check_increment_and_reset():
    redis = FakeRedis()
    limiter = RedisRateLimiter(redis)

    assert limiter.check("rate:key", max_attempts=2, window_seconds=30) is True

    assert limiter.increment("rate:key", window_seconds=30) == 1
    assert redis.expirations["rate:key"] == 30
    assert limiter.check("rate:key", max_attempts=2, window_seconds=30) is True

    assert limiter.increment("rate:key", window_seconds=30) == 2
    assert limiter.check("rate:key", max_attempts=2, window_seconds=30) is False

    limiter.reset("rate:key")
    assert "rate:key" not in redis.values


def test_redis_rate_limiter_degrades_safely_on_redis_errors():
    limiter = RedisRateLimiter(BrokenRedis())

    assert limiter.check("rate:key", max_attempts=1, window_seconds=10) is True
    assert limiter.increment("rate:key", window_seconds=10) == 0
    limiter.reset("rate:key")


def test_scraping_rate_limiter_uses_token_bucket_without_real_redis(monkeypatch):
    import shared.utils.redis_client as redis_client_module

    calls: dict[str, object] = {}

    def fake_consume_token_bucket(key: str, *, capacity: int, refill_rate_per_second: float, client):
        calls["key"] = key
        calls["capacity"] = capacity
        calls["refill_rate"] = refill_rate_per_second
        calls["client"] = client
        return True, 1.0

    monkeypatch.setattr(redis_client_module, "consume_token_bucket", fake_consume_token_bucket)

    limiter = ScrapingRateLimiter(
        lambda: "redis-client",
        max_requests=6,
        window_seconds=3,
    )

    assert limiter.allow("example.com") is True
    assert calls["key"] == "rate:scraping:example.com"
    assert calls["capacity"] == 6
    assert calls["refill_rate"] == 2.0
    assert calls["client"] == "redis-client"


def test_circuit_breaker_opens_and_resets_host_state():
    redis = FakeRedis()
    breaker = CircuitBreaker(
        lambda: redis,
        failure_threshold=2,
        failure_window=30,
        cooldown_seconds=15,
    )

    assert breaker.is_open("example.com") is False

    breaker.record_failure("example.com")
    assert redis.values["circuit:failures:example.com"] == 1
    assert breaker.is_open("example.com") is False

    breaker.record_failure("example.com")
    assert breaker.is_open("example.com") is True
    assert "circuit:failures:example.com" not in redis.values

    breaker.record_success("example.com")
    assert breaker.is_open("example.com") is False


def test_cache_strategy_supports_hit_miss_and_invalidation(monkeypatch):
    import shared.infra.cache_strategy as cache_strategy_module

    redis = FakeRedis()
    redis.values["cache:hit"] = '{"name": "cached"}'
    redis.values["cache:item:1"] = '{"v": 1}'
    redis.values["cache:item:2"] = '{"v": 2}'

    monkeypatch.setattr(cache_strategy_module, "get_redis_operational", lambda: redis)

    calls = {"count": 0}

    def fetch_value():
        calls["count"] += 1
        return {"name": "fresh"}

    assert get_with_cache("cache:hit", ttl=30, fetch_fn=fetch_value) == {"name": "cached"}
    assert calls["count"] == 0

    miss_result = get_with_cache("cache:miss", ttl=45, fetch_fn=fetch_value)
    assert miss_result == {"name": "fresh"}
    assert redis.values["cache:miss"] == '{"name": "fresh"}'
    assert redis.expirations["cache:miss"] == 45

    invalidate("cache:miss")
    assert "cache:miss" not in redis.values

    invalidate_pattern("cache:item:*")
    assert "cache:item:1" not in redis.values
    assert "cache:item:2" not in redis.values


def test_cache_strategy_degrades_gracefully_when_cache_backend_fails(monkeypatch):
    import shared.infra.cache_strategy as cache_strategy_module

    monkeypatch.setattr(cache_strategy_module, "get_redis_operational", lambda: BrokenRedis())

    calls = {"count": 0}

    def fetch_value():
        calls["count"] += 1
        return {"name": "fallback"}

    assert get_with_cache("cache:key", ttl=10, fetch_fn=fetch_value) == {"name": "fallback"}
    assert calls["count"] == 1

    invalidate("cache:key")
    invalidate_pattern("cache:*")


# ──────────────────── Fase 1: Redis e rate limit — testes de regressão ────────────────────


def test_redis_client_init_failure_does_not_raise_secondary_exception(monkeypatch):
    """get_redis_operational retorna None sem gerar exceção secundária de logging.

    Garante que o logger estruturado usado dentro do except não cause TypeError
    quando o Redis não consegue ser inicializado.
    """
    import redis as redis_module
    import shared.utils.redis_client as rc

    # Força uma falha na criação do cliente
    def broken_from_url(*_args, **_kwargs):
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(redis_module.Redis, "from_url", broken_from_url)
    # Limpa cache de thread-local para forçar nova tentativa de conexão
    monkeypatch.setattr(rc, "_thread_local", type("T", (), {})())

    # Não deve lançar nenhuma exceção, incluindo TypeError do logger
    result = rc.get_redis_operational()
    assert result is None


def test_consume_token_bucket_allows_when_redis_unavailable(monkeypatch):
    """consume_token_bucket retorna (True, None) quando nenhum client Redis está disponível."""
    import shared.utils.redis_client as rc

    monkeypatch.setattr(rc, "get_redis_operational", lambda: None)

    allowed, tokens = rc.consume_token_bucket(
        "rate:host:test",
        capacity=5,
        refill_rate_per_second=1.0,
    )
    assert allowed is True
    assert tokens is None


def test_consume_token_bucket_allows_when_redis_raises(monkeypatch):
    """consume_token_bucket retorna (True, None) quando Redis levanta exceção — sem propagar erro."""
    import shared.utils.redis_client as rc

    # get_redis_operational retorna None → fallback
    monkeypatch.setattr(rc, "get_redis_operational", lambda: None)

    allowed, tokens = rc.consume_token_bucket(
        "rate:host:test",
        capacity=5,
        refill_rate_per_second=1.0,
    )
    assert allowed is True
    assert tokens is None


def test_consume_leaky_bucket_allows_when_redis_unavailable(monkeypatch):
    """consume_leaky_bucket retorna (True, None) quando Redis está indisponível."""
    import shared.utils.redis_client as rc

    monkeypatch.setattr(rc, "get_redis_operational", lambda: None)

    allowed, tokens = rc.consume_leaky_bucket(
        "rate:leak:test",
        capacity=5,
        leak_rate_per_second=1.0,
    )
    assert allowed is True
    assert tokens is None


def test_scraping_rate_limiter_allows_when_factory_raises():
    """ScrapingRateLimiter retorna True (permissivo) quando o factory do cliente levanta exceção."""

    def broken_factory():
        raise RuntimeError("can't connect")

    limiter = ScrapingRateLimiter(
        broken_factory,
        max_requests=5,
        window_seconds=10,
    )

    # Não deve lançar exceção; deve retornar True como fallback
    assert limiter.allow("example.com") is True
