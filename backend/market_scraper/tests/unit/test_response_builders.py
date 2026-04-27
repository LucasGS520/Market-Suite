"""Testes unitários para utils/response_builder.py.

Cobre as APIs públicas de construção de respostas HTTP:
- build_parser_response (response_builder)
- build_no_result_response (response_builder)
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from shared.schemas.shared_schemas_scraper import (
    SCRAPER_CONTRACT_VERSION,
    SCRAPER_CONTRACT_VERSION_HEADER,
)
from market_scraper.utils.response_builder import (
    build_no_result_response,
    build_parser_response,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _silent_logger() -> MagicMock:
    """Logger stub que não emite nada — evita output em testes."""
    return MagicMock()


def _post_process_result(
    *,
    name: str = "Produto Teste",
    current_price: Decimal | None = Decimal("199.90"),
    availability: bool = True,
    url: str = "https://example.com/product",
    source: str = "example.com",
):
    """Cria PostProcessResult mínimo para testes de build_parser_response."""
    from market_scraper.domain.dtos import PostProcessResult

    return PostProcessResult(
        name=name,
        current_price=current_price,
        currency=None,
        availability=availability,
        last_status="available",
        url=url,
        source=source,
    )


# ── build_no_result_response ─────────────────────────────────────────────────


def test_build_no_result_response_returns_422():
    response = build_no_result_response(
        reason_code="extraction_empty",
        trace_id="trace-no-result",
        request_logger=_silent_logger(),
    )
    assert response.status_code == 422


def test_build_no_result_response_body_has_canonical_error_code():
    import json
    response = build_no_result_response(
        reason_code="extraction_empty",
        trace_id="trace-no-result",
        request_logger=_silent_logger(),
    )
    body = json.loads(response.body)
    assert body["error_code"] == "no_result"
    assert body["trace_id"] == "trace-no-result"
    assert body["message"]


def test_build_no_result_response_sets_contract_version_header():
    response = build_no_result_response(
        reason_code=None,
        trace_id="trace-header",
        request_logger=_silent_logger(),
    )
    assert response.headers[SCRAPER_CONTRACT_VERSION_HEADER] == SCRAPER_CONTRACT_VERSION


def test_build_no_result_response_emits_warning_log():
    logger = _silent_logger()
    build_no_result_response(
        reason_code="html_too_short",
        trace_id="trace-log",
        request_logger=logger,
    )
    logger.warning.assert_called_once()
    call_kwargs = logger.warning.call_args.kwargs
    assert call_kwargs.get("reason_code") == "html_too_short"


def test_build_no_result_response_handles_none_reason_code():
    import json
    response = build_no_result_response(
        reason_code=None,
        trace_id="trace-none",
        request_logger=_silent_logger(),
    )
    body = json.loads(response.body)
    assert body["error_code"] == "no_result"


# ── build_parser_response / alias ────────────────────────────────────────────


def test_build_parser_response_maps_fields_correctly():
    result = _post_process_result(
        name="Produto X",
        current_price=Decimal("299.00"),
        availability=True,
        url="https://example.com/p/x",
        source="example.com",
    )
    response = build_parser_response(result, request_logger=_silent_logger())
    assert response.name == "Produto X"
    assert response.current_price == Decimal("299.00")
    assert response.availability is True
    assert str(response.url) == "https://example.com/p/x"
    assert response.source == "example.com"

