"""Testes unitários para infra/errors_map.py.

Valida que a taxonomia canônica de erros mapeia corretamente
error_codes internos → (UrlIssue, http_status).
"""

from __future__ import annotations

import pytest
from fastapi import status as http_status

from market_scraper.infra.errors_map import COLLECTION_ERROR_MAP, map_collection_error


# ── Cobertura dos mapeamentos conhecidos ──────────────────────────────────────


@pytest.mark.parametrize(
    "error_code, expected_issue_code, expected_status",
    [
        ("anti_bot_page", "anti_bot_page", http_status.HTTP_429_TOO_MANY_REQUESTS),
        ("rate_limiter_cooldown", "rate_limiter_cooldown", http_status.HTTP_429_TOO_MANY_REQUESTS),
        ("too_many_redirects", "too_many_redirects", http_status.HTTP_422_UNPROCESSABLE_ENTITY),
        ("invalid_url", "invalid_url", http_status.HTTP_422_UNPROCESSABLE_ENTITY),
        ("playwright_timeout", "playwright_timeout", http_status.HTTP_504_GATEWAY_TIMEOUT),
        ("playwright_fetch_error", "playwright_fetch_error", http_status.HTTP_503_SERVICE_UNAVAILABLE),
        ("playwright_not_ready", "pipeline_degraded", http_status.HTTP_503_SERVICE_UNAVAILABLE),
        ("pipeline_degraded", "pipeline_degraded", http_status.HTTP_503_SERVICE_UNAVAILABLE),
    ],
)
def test_map_collection_error_known_codes(error_code, expected_issue_code, expected_status):
    issue, status = map_collection_error(error_code)
    assert issue.code == expected_issue_code
    assert status == expected_status


def test_map_collection_error_unknown_code_returns_upstream_error():
    """Código desconhecido cai no fallback: upstream_error / 503."""
    issue, status = map_collection_error("some_unknown_code")
    assert issue.code == "upstream_error"
    assert status == http_status.HTTP_503_SERVICE_UNAVAILABLE


def test_map_collection_error_none_input_returns_upstream_error():
    issue, status = map_collection_error(None)
    assert issue.code == "upstream_error"
    assert status == http_status.HTTP_503_SERVICE_UNAVAILABLE


def test_map_collection_error_empty_string_returns_upstream_error():
    issue, status = map_collection_error("")
    assert issue.code == "upstream_error"
    assert status == http_status.HTTP_503_SERVICE_UNAVAILABLE


def test_map_collection_error_returns_issue_with_message():
    """Cada mapeamento inclui mensagem não vazia."""
    issue, _ = map_collection_error("anti_bot_page")
    assert issue.message


def test_collection_error_map_covers_all_expected_codes():
    """Garante que a taxonomia não perde entradas silenciosamente."""
    expected_codes = {
        "anti_bot_page",
        "rate_limiter_cooldown",
        "too_many_redirects",
        "invalid_url",
        "playwright_timeout",
        "playwright_fetch_error",
        "playwright_not_ready",
        "pipeline_degraded",
    }
    assert expected_codes == set(COLLECTION_ERROR_MAP.keys())
