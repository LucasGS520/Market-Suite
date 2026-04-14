from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

import pytest

import market_alert.collectors.tasks.collector_product_task as collector_task_module
from market_alert.collectors.utils.collector_result import (
    _resolve_outcome,
    _resolve_reason_from_result,
)
from shared.clients.scraper.scraper_client import ScraperClientError
from shared.schemas.collection_catalog import (
    OUTCOME_SUCCESS,
    REASON_CHALLENGE_DETECTED,
    REASON_NAVIGATION_TIMEOUT,
    REASON_PARSE_EMPTY,
    REASON_ROBOTS_DISALLOWED,
    REASON_SCRAPER_UNAVAILABLE,
)
from shared.schemas.shared_schemas_scraper import ScrapeResult


pytestmark = pytest.mark.unit


class _SessionStub:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@contextmanager
def _task_request(task, **kwargs):
    task.push_request(**kwargs)
    try:
        yield
    finally:
        task.pop_request()


def _valid_collection_payload(**overrides: str) -> dict[str, str]:
    payload = {
        "version": 1,
        "kind": "monitored",
        "monitored_id": str(uuid4()),
        "url": "https://store.example.com/products/contract-phase-6",
        "trace_id": str(uuid4()),
        "user_id": str(uuid4()),
        "name": "Produto contratual",
    }
    payload.update(overrides)
    return payload


def test_scraper_alert_contract_keeps_success_without_semantic_error() -> None:
    result = ScrapeResult(
        status="success",
        product_id="monitored-1",
        http_status=200,
    )

    reason = _resolve_reason_from_result(result)
    outcome = _resolve_outcome(
        "monitored",
        result,
        lock_status="not_used",
        reason=reason,
    )

    assert reason is None
    assert outcome == OUTCOME_SUCCESS


@pytest.mark.parametrize(
    ("error_code", "http_status", "expected_reason"),
    [
        ("no_result", 422, REASON_PARSE_EMPTY),
        ("anti_bot_page", 422, REASON_CHALLENGE_DETECTED),
        ("unsupported_by_robots", 403, REASON_ROBOTS_DISALLOWED),
        ("pipeline_timeout", 422, REASON_NAVIGATION_TIMEOUT),
    ],
    ids=[
        "no_result",
        "anti_bot_page",
        "unsupported_by_robots",
        "pipeline_timeout",
    ],
)
def test_scraper_alert_contract_maps_scraper_error_codes_to_catalog_reason(
    error_code: str,
    http_status: int,
    expected_reason: str,
) -> None:
    result = ScrapeResult(
        status="error",
        product_id="monitored-1",
        http_status=http_status,
        error_code=error_code,
    )

    assert _resolve_reason_from_result(result) == expected_reason


@pytest.mark.parametrize("status_code", [503, 504], ids=["503", "504"])
def test_collect_product_task_maps_transport_unavailability_to_scraper_unavailable(
    status_code: int,
    monkeypatch,
) -> None:
    payload = _valid_collection_payload()

    monkeypatch.setattr(collector_task_module, "SessionLocal", lambda: _SessionStub())
    monkeypatch.setattr(collector_task_module, "is_scraping_suspended", lambda: False)
    monkeypatch.setattr(
        collector_task_module,
        "acquire_product_lock",
        lambda *args, **kwargs: (True, "lock-owner"),
    )
    monkeypatch.setattr(collector_task_module, "release_product_lock", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        collector_task_module,
        "collect_product",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ScraperClientError(
                "scraper indisponivel",
                status_code=status_code,
            )
        ),
    )
    monkeypatch.setattr(collector_task_module, "_should_block_invalid_url", lambda result: False)
    monkeypatch.setattr(
        collector_task_module,
        "_should_schedule_temporary_retry",
        lambda result, reason: False,
    )

    with _task_request(
        collector_task_module.collect_product_task,
        id=f"collect-task-unavailable-{status_code}",
        retries=0,
        delivery_info={"routing_key": "scraping"},
    ):
        result = collector_task_module.collect_product_task.run(payload=payload)

    assert result == {
        "outcome": "error",
        "status": "error",
        "reason": REASON_SCRAPER_UNAVAILABLE,
        "next_retry_at": None,
        "product_id": payload["monitored_id"],
    }
