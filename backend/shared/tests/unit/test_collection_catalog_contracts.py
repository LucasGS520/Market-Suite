from __future__ import annotations

import pytest

from market_alert.collectors.utils.collector_result import (
    SCRAPER_CONTRACT_ERROR_CODE_TO_REASON,
    _resolve_outcome,
    _resolve_reason_from_result,
)
from shared.schemas.collection_catalog import (
    WORKFLOW_BACKOFF,
    WORKFLOW_WAITING_TIMER,
    REASON_ERROR_CLASS,
    get_error_class,
    get_workflow_decision,
    has_source_integrity,
)
from shared.schemas.shared_schemas_scraper import (
    SCRAPER_ALLOWED_ERROR_CODES,
    ScrapeResult,
)


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("status", "error_code", "http_status", "expected_reason", "expected_outcome", "expected_category", "expected_action", "expected_source_integrity"),
    [
        ("error", "rate_limit", 429, "http_429", "error", "transient", WORKFLOW_BACKOFF, False),
        ("error", "anti_bot_page", 403, "challenge_detected", "error", "transient", WORKFLOW_BACKOFF, False),
        ("error", "timeout", 504, "navigation_timeout", "error", "transient", WORKFLOW_BACKOFF, False),
        ("error", "selector_missing", 422, "selector_missing", "error", "structural", WORKFLOW_BACKOFF, False),
        ("error", "parse_price_failed", 422, "parse_price_failed", "error", "structural", WORKFLOW_BACKOFF, False),
        ("no_result", "no_result", 422, "parse_empty", "no_result", "domain_empty", WORKFLOW_BACKOFF, True),
        ("not_modified", None, 304, None, "not_modified", None, WORKFLOW_WAITING_TIMER, True),
        ("no_result", "lock_skipped", 200, "lock_skipped", "no_result", "neutral", WORKFLOW_WAITING_TIMER, False),
    ],
)
def test_collection_contract_matrix_for_critical_reasons(
    status: str,
    error_code: str | None,
    http_status: int | None,
    expected_reason: str | None,
    expected_outcome: str,
    expected_category: str | None,
    expected_action: str,
    expected_source_integrity: bool,
) -> None:
    result = ScrapeResult(
        status=status,
        error_code=error_code,
        product_id="product-1",
        http_status=http_status,
    )

    reason = _resolve_reason_from_result(result)
    outcome = _resolve_outcome("monitored", result, lock_status="acquired", reason=reason)

    assert reason == expected_reason
    assert outcome == expected_outcome
    assert get_workflow_decision(outcome, reason) == expected_action
    assert has_source_integrity(outcome, reason) is expected_source_integrity
    if expected_category is None:
        assert reason is None
    else:
        assert get_error_class(reason) == expected_category


def test_all_documented_scraper_error_codes_map_to_catalog_reasons() -> None:
    assert set(SCRAPER_CONTRACT_ERROR_CODE_TO_REASON) == set(SCRAPER_ALLOWED_ERROR_CODES)

    for error_code in SCRAPER_ALLOWED_ERROR_CODES:
        reason = SCRAPER_CONTRACT_ERROR_CODE_TO_REASON[error_code]
        assert reason in REASON_ERROR_CLASS


@pytest.mark.parametrize(
    ("error_code", "expected_reason"),
    [
        ("invalid_url", "invalid_url"),
        ("blocked_host", "blocked_host"),
        ("unsupported_by_robots", "robots_disallowed"),
        ("too_many_redirects", "invalid_url"),
        ("anti_bot_page", "challenge_detected"),
        ("no_result", "parse_empty"),
        ("pipeline_timeout", "navigation_timeout"),
    ],
)
def test_contract_error_codes_resolve_to_single_catalog_reason(
    error_code: str,
    expected_reason: str,
) -> None:
    result = ScrapeResult(
        status="error" if error_code != "no_result" else "no_result",
        error_code=error_code,
        product_id="product-1",
        http_status=504 if error_code == "pipeline_timeout" else 422,
    )

    assert _resolve_reason_from_result(result) == expected_reason
