from __future__ import annotations

import json
from decimal import Decimal

import structlog

from market_scraper.routes.response_helpers import (
    _extract_acquisition_payload,
    _extract_additional_payload,
    _map_http_download_issue,
    _sanitize_payload,
    build_no_result_response,
    build_success_response,
)
from market_scraper.services.synergic_pipeline import (
    PipelineContext,
    PipelineOutcome,
    StepExecution,
)


class _LoggerSpy:
    def __init__(self) -> None:
        self.warning_calls: list[tuple[str, dict[str, object]]] = []
        self.info_calls: list[tuple[str, dict[str, object]]] = []

    def warning(self, event: str, **kwargs) -> None:
        self.warning_calls.append((event, kwargs))

    def info(self, event: str, **kwargs) -> None:
        self.info_calls.append((event, kwargs))


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


def test_map_http_download_issue_handles_robots_and_invalid_url():
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )

    robots_outcome = PipelineOutcome(
        status="error",
        context=context,
        steps=[
            StepExecution(
                name="fetch_html",
                status="error",
                duration_seconds=0.01,
                message="unsupported_by_robots",
            )
        ],
    )
    invalid_url_outcome = PipelineOutcome(
        status="error",
        context=context,
        steps=[
            StepExecution(
                name="fetch_html",
                status="error",
                duration_seconds=0.01,
                message="invalid_url",
            )
        ],
    )

    robots_issue, robots_status = _map_http_download_issue(robots_outcome)
    invalid_issue, invalid_status = _map_http_download_issue(invalid_url_outcome)

    assert robots_issue.code == "unsupported_by_robots"
    assert robots_status == 403
    assert invalid_issue.code == "invalid_url"
    assert invalid_status == 422


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


def test_extract_acquisition_payload_returns_none_without_fetch_telemetry():
    assert _extract_acquisition_payload({}) is None


def test_build_success_response_merges_inferred_state_and_extra_payload():
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )
    context.data["availability_inferred"] = False
    context.data["last_status_inferred"] = "not_found"
    context.data["layer_used"] = "curl_cffi"
    context.data["fallback_taken"] = False
    context.data["classification_reason"] = "html_valid"
    context.data["http_status"] = 200
    context.data["anti_bot_detected"] = False
    context.data["anti_bot_pattern"] = None
    context.data["anti_bot_bypassed"] = False
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
    assert response.payload == {
        "sku": "ABC-1",
        "acquisition": {
            "layer_used": "curl_cffi",
            "fallback_taken": False,
            "classification_reason": "html_valid",
            "http_status": 200,
            "anti_bot_detected": False,
            "anti_bot_pattern": None,
            "anti_bot_bypassed": False,
        },
    }


def test_build_success_response_uses_marketplace_fallback_and_context_last_status():
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )
    context.data["last_status"] = "temporarily_unavailable"
    outcome = PipelineOutcome(status="success", context=context)
    request_logger = _LoggerSpy()

    response = build_success_response(
        {
            "name": "Produto Y",
            "current_price": None,
            "source": None,
            "marketplace": "fallback.example.com",
            "rank": 7,
        },
        normalized_url="https://example.com/product",
        outcome=outcome,
        request_logger=request_logger,
        current_price=None,
    )

    assert response.source == "fallback.example.com"
    assert response.last_status == "temporarily_unavailable"
    assert response.payload == {"rank": 7}
    assert request_logger.info_calls[0][0] == "parse_success"


def test_sanitize_payload_masks_url_for_logging():
    assert _sanitize_payload("https://user:pass@example.com/product?token=123") == {
        "url": "https://user:pass@example.com/product?token=%5BREDACTED%5D"
    }


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
        "message": "N\u00e3o foi poss\u00edvel extrair dados do produto",
        "error_code": "no_result",
        "trace_id": "trace-1",
    }


def test_build_no_result_response_logs_validation_failure_metadata():
    context = PipelineContext(
        url="https://example.com/product",
        source="example.com",
        default_step_timeout=1.0,
    )
    context.data["validation_failures"] = [
        {
            "step": "generic_fallback_parser",
            "reason_code": "price_invalid",
            "reason_message": "Preco ausente ou invalido",
            "parser_name": "parse_generic_html",
            "dump_path": "/tmp/dump.html",
        }
    ]
    outcome = PipelineOutcome(status="no_result", context=context)
    request_logger = _LoggerSpy()

    response = build_no_result_response(
        outcome=outcome,
        request_logger=request_logger,
        trace_id="trace-2",
    )

    assert response.status_code == 422
    # parse_no_result é o único log — parse_error foi suprimido para evitar duplicação
    warning_events = [event for event, _fields in request_logger.warning_calls]
    assert warning_events == ["parse_no_result"]
    parse_no_result_fields = request_logger.warning_calls[0][1]
    assert parse_no_result_fields["reason_code"] == "price_invalid"
    assert parse_no_result_fields["reason_message"] == "Preco ausente ou invalido"
    assert parse_no_result_fields["parser_name"] == "parse_generic_html"
    assert parse_no_result_fields["dump_path"] == "/tmp/dump.html"


def test_map_http_download_issue_pipeline_degraded_returns_503():
    """pipeline_degraded (SCALE sem fallback de browser) → 503."""
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
                name="cascade_fetch",
                status="error",
                duration_seconds=0.1,
                message="pipeline_degraded",
            )
        ],
    )

    issue, status_code = _map_http_download_issue(outcome)

    assert issue.code == "pipeline_degraded"
    assert status_code == 503


def test_map_http_download_issue_playwright_not_ready_returns_503():
    """playwright_not_ready continua mapeado para 503 via salvaguarda operacional."""
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
                name="playwright_fetch",
                status="error",
                duration_seconds=0.1,
                message="playwright_not_ready",
            )
        ],
    )

    issue, status_code = _map_http_download_issue(outcome)

    assert issue.code == "pipeline_degraded"
    assert status_code == 503
