from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from shared.scheduling.context import SchedulingContext


pytestmark = pytest.mark.unit


class FakeIdempotencyRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex
        return True

    def get(self, key: str) -> str | None:
        return self.values.get(key)


class FakeScriptRedis:
    def __init__(self, result: list[float | int]) -> None:
        self.result = result
        self.registered_scripts: list[str] = []
        self.calls: list[dict[str, object]] = []

    def register_script(self, script_source: str):
        self.registered_scripts.append(script_source)

        def _script(*, keys, args):
            self.calls.append({"keys": keys, "args": args})
            return list(self.result)

        return _script


def test_idempotency_register_store_and_replay(monkeypatch):
    import shared.infra.redis.idempotency as module

    redis = FakeIdempotencyRedis()
    monkeypatch.setattr(module, "get_redis_operational", lambda: redis)

    registered = module.register_idempotency_key(
        namespace="products",
        key="abc-123",
        owner="user-1",
        ttl_seconds=120,
    )
    assert registered == module.IdempotencyRecord(
        is_new=True,
        owner="user-1",
        response=None,
        status_code=None,
    )

    module.store_idempotency_response(
        namespace="products",
        key="abc-123",
        owner="user-1",
        ttl_seconds=120,
        response={"id": "prod-1"},
        status_code=202,
    )

    replay = module.register_idempotency_key(
        namespace="products",
        key="abc-123",
        owner="user-1",
        ttl_seconds=120,
    )
    assert replay == module.IdempotencyRecord(
        is_new=False,
        owner="user-1",
        response={"id": "prod-1"},
        status_code=202,
    )


def test_idempotency_rejects_conflicting_owner(monkeypatch):
    import shared.infra.redis.idempotency as module

    redis = FakeIdempotencyRedis()
    monkeypatch.setattr(module, "get_redis_operational", lambda: redis)

    module.register_idempotency_key(
        namespace="notifications",
        key="same-key",
        owner="user-1",
        ttl_seconds=60,
    )

    with pytest.raises(module.IdempotencyOwnershipError):
        module.register_idempotency_key(
            namespace="notifications",
            key="same-key",
            owner="user-2",
            ttl_seconds=60,
        )


def test_scheduler_returns_immediate_for_pending_without_first_check():
    import shared.scheduling.scheduler as module

    reference_time = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    ctx = SchedulingContext(
        status="pending",
        last_checked=None,
        last_price_change_at=None,
        group_collected_at=None,
        last_scraped_at=None,
        created_at=reference_time,
        next_check_at=None,
    )

    decision = module.calculate_schedule(ctx, reference_time=reference_time)

    assert decision.interval_seconds == 0
    assert decision.next_check_at == reference_time
    assert decision.reason == "initial_pending_immediate"


def test_scheduler_applies_transition_and_retry_cooldown_floor(monkeypatch):
    import shared.scheduling.scheduler as module

    reference_time = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(module, "_random_interval", lambda min_seconds, max_seconds: 30)
    monkeypatch.setattr(module._cfg, "SCRAPER_RATE_LIMIT_COOLDOWN_SECONDS", 120, raising=False)

    ctx = SchedulingContext(
        status="active",
        last_checked=reference_time - timedelta(hours=1),
        last_price_change_at=reference_time - timedelta(days=10),
        group_collected_at=None,
        last_scraped_at=reference_time - timedelta(hours=1),
        created_at=reference_time - timedelta(days=30),
        next_check_at=None,
        stability_score=2,
    )

    decision = module.calculate_schedule(
        ctx,
        reference_time=reference_time,
        event_type=module.EVENT_PRICE_CHANGED,
        retry_context=module.RetryContext(
            reason="429",
            next_retry_at=reference_time + timedelta(seconds=20),
        ),
    )

    assert decision.stability_score == module.STABILITY_UNSTABLE
    assert decision.reason == "retry_cooldown_floor"
    assert decision.next_check_at == reference_time + timedelta(seconds=120)


def test_cache_invalidator_targets_expected_keys(monkeypatch):
    import shared.utils.cache_invalidator as module

    invalidated: list[str] = []
    invalidated_patterns: list[str] = []

    monkeypatch.setattr(module, "invalidate", lambda key: invalidated.append(key))
    monkeypatch.setattr(module, "invalidate_pattern", lambda pattern: invalidated_patterns.append(pattern))

    module.invalidate_product_cache("42")
    module.invalidate_product_price("42")
    module.invalidate_product_comparison("42")
    module.invalidate_robots("example.com")

    assert invalidated_patterns == ["cache:product:42:*"]
    assert invalidated == [
        "cache:product:42:price",
        "cache:product:42:comparison",
        "robots:example.com",
    ]


def test_leaky_bucket_executes_registered_script_and_reuses_cache(monkeypatch):
    import shared.utils.redis_client as module

    redis = FakeScriptRedis([1, 2.5])
    monkeypatch.setattr(module, "get_redis_operational", lambda: redis)
    module._registered_scripts.clear()

    first = module.consume_leaky_bucket(
        "rate:user:1",
        capacity=5,
        leak_rate_per_second=1.0,
        ttl_seconds=10,
        now=100.0,
    )
    second = module.consume_leaky_bucket(
        "rate:user:1",
        capacity=5,
        leak_rate_per_second=1.0,
        ttl_seconds=10,
        now=101.0,
    )

    assert first == (True, 2.5)
    assert second == (True, 2.5)
    assert len(redis.registered_scripts) == 1
    assert redis.calls[0]["keys"] == ["rate:user:1"]


def test_token_bucket_executes_registered_script_and_reuses_cache(monkeypatch):
    import shared.utils.redis_client as module

    redis = FakeScriptRedis([0, 0.0])
    module._registered_token_bucket_scripts.clear()

    first = module.consume_token_bucket(
        "rate:host:example.com",
        capacity=3,
        refill_rate_per_second=0.5,
        ttl_seconds=12,
        now=200.0,
        client=redis,
    )
    second = module.consume_token_bucket(
        "rate:host:example.com",
        capacity=3,
        refill_rate_per_second=0.5,
        ttl_seconds=12,
        now=201.0,
        client=redis,
    )

    assert first == (False, 0.0)
    assert second == (False, 0.0)
    assert len(redis.registered_scripts) == 1
    assert redis.calls[0]["keys"] == ["rate:host:example.com"]
