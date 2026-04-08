from __future__ import annotations

import json
from decimal import Decimal

import structlog

from market_scraper.routes.response_helpers import (
    _extract_additional_payload,
    _map_http_download_issue,
    build_no_result_response,
    build_success_response,
)
from market_scraper.services.synergic_pipeline import (
    PipelineContext,
    PipelineOutcome,
    StepExecution,
)


def test_map_http_download_issue_returns_expected_issue_codes():
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )

    outcome = PipelineOutcome(
        status="error",
        context=context,
        steps=[
            StepExecution(
                name="fetch_html",
                status="error",
                duration_seconds=0.01,
                message="too_many_redirects",
            )
        ],
    )

    issue, status_code = _map_http_download_issue(outcome)

    assert issue.code == "too_many_redirects"
    assert status_code == 422


def test_extract_additional_payload_filters_standard_fields():
    extras = _extract_additional_payload(
        {
            "name": "Produto",
            "current_price": "10.00",
            "url": "https://example.com/product",
            "source": "example.com",
            "marketplace": "example.com",
            "currency": "BRL",
            "availability": True,
            "last_status": "available",
            "etag": "abc",
            "sku": "SKU-1",
            "rank": 3,
        }
    )

    assert extras == {"sku": "SKU-1", "rank": 3}


def test_build_success_response_merges_inferred_state_and_extra_payload():
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )
    context.data["availability_inferred"] = False
    context.data["last_status_inferred"] = "not_found"
    outcome = PipelineOutcome(status="success", context=context)

    response = build_success_response(
        {
            "name": " Produto X ",
            "current_price": "10.00",
            "source": "example.com",
            "sku": "ABC-1",
        },
        normalized_url="https://example.com/product",
        outcome=outcome,
        request_logger=structlog.get_logger("test"),
        current_price=Decimal("10.00"),
    )

    assert response.name == "Produto X"
    assert response.availability is False
    assert response.last_status == "not_found"
    assert response.payload == {"sku": "ABC-1"}


def test_build_no_result_response_returns_standard_error_body():
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )
    context.data["validation_failures"] = [
        {
            "step": "json_ld_parser",
            "reason_code": "missing_name",
            "reason_message": "Nome ausente",
            "parser_name": "parse_with_extruct",
        }
    ]
    outcome = PipelineOutcome(status="no_result", context=context)

    response = build_no_result_response(
        outcome=outcome,
        request_logger=structlog.get_logger("test"),
        trace_id="trace-1",
    )

    assert response.status_code == 422
    assert json.loads(response.body) == {
        "message": "Não foi possível extrair dados do produto",
        "error_code": "no_result",
        "trace_id": "trace-1",
    }
