from __future__ import annotations

from datetime import datetime, timezone

import pytest

import market_alert.infrastructure.celery.retry_policies as retry_policies_module
from shared.schemas.collection_catalog import (
    REASON_CHALLENGE_DETECTED,
    REASON_HTTP_429,
    REASON_NAVIGATION_TIMEOUT,
)


pytestmark = pytest.mark.unit


def test_is_cooldown_reason_accepts_catalog_reasons() -> None:
    assert retry_policies_module.RetryPolicy.is_cooldown_reason(REASON_HTTP_429) is True
    assert retry_policies_module.RetryPolicy.is_cooldown_reason(REASON_CHALLENGE_DETECTED) is True
    assert retry_policies_module.RetryPolicy.is_cooldown_reason(REASON_NAVIGATION_TIMEOUT) is False


def test_compute_scrape_retry_delay_uses_retry_after_for_catalog_cooldown_reason(monkeypatch) -> None:
    captured: list[dict[str, object]] = []

    def fake_compute(attempt: int, *, retry_after: int | None = None, max_seconds: int = 0) -> int:
        captured.append(
            {
                "attempt": attempt,
                "retry_after": retry_after,
                "max_seconds": max_seconds,
            }
        )
        return 45

    monkeypatch.setattr(retry_policies_module, "_compute_scrape_retry_delay", fake_compute)

    delay = retry_policies_module.RetryPolicy.compute_scrape_retry_delay(
        REASON_HTTP_429,
        2,
        retry_after=120,
        max_seconds=300,
    )

    assert delay == 45
    assert captured == [{"attempt": 2, "retry_after": 120, "max_seconds": 300}]


def test_compute_scrape_retry_delay_ignores_retry_after_for_non_cooldown_reason(monkeypatch) -> None:
    captured: list[dict[str, object]] = []

    def fake_compute(attempt: int, *, retry_after: int | None = None, max_seconds: int = 0) -> int:
        captured.append(
            {
                "attempt": attempt,
                "retry_after": retry_after,
                "max_seconds": max_seconds,
            }
        )
        return 30

    monkeypatch.setattr(retry_policies_module, "_compute_scrape_retry_delay", fake_compute)

    delay = retry_policies_module.RetryPolicy.compute_scrape_retry_delay(
        REASON_NAVIGATION_TIMEOUT,
        2,
        retry_after=120,
        max_seconds=300,
    )

    assert delay == 30
    assert captured == [{"attempt": 2, "retry_after": None, "max_seconds": 300}]


def test_should_retry_scrape_failure_returns_next_retry_at_for_catalog_reason(monkeypatch) -> None:
    monkeypatch.setattr(
        retry_policies_module.RetryPolicy,
        "compute_scrape_retry_delay",
        staticmethod(lambda reason, attempt, retry_after=None, max_seconds=None: 90.0),
    )
    now = datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc)

    should_retry, next_retry_at = retry_policies_module.RetryPolicy.should_retry_scrape_failure(
        REASON_CHALLENGE_DETECTED,
        1,
        retry_after=180,
        now=now,
    )

    assert should_retry is True
    assert next_retry_at is not None
    assert (next_retry_at - now).total_seconds() == 90
