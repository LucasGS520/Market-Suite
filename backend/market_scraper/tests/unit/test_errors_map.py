"""Testes unitários para infra/errors_map.py.

Valida que a taxonomia canônica de erros mapeia corretamente
error_codes internos → (UrlIssue, http_status).
"""

from __future__ import annotations

import pytest
from fastapi import status as http_status

from market_scraper.infra.errors_map import (
    CACHE_INVALIDATING_ERROR_CODES,
    COLLECTION_ERROR_MAP,
    HTTP_TIMEOUT_ORIGIN_OVERRIDES,
    map_collection_error,
)


# ── Cobertura dos mapeamentos conhecidos ──────────────────────────────────────


@pytest.mark.parametrize(
    "error_code, expected_issue_code, expected_status",
    [
        # Anti-bot / rate limit (nosso rate limiter e proteção anti-bot)
        ("anti_bot_page", "anti_bot_page", http_status.HTTP_429_TOO_MANY_REQUESTS),
        ("rate_limiter_cooldown", "rate_limiter_cooldown", http_status.HTTP_429_TOO_MANY_REQUESTS),
        # URL
        ("too_many_redirects", "too_many_redirects", http_status.HTTP_422_UNPROCESSABLE_ENTITY),
        ("invalid_url", "invalid_url", http_status.HTTP_422_UNPROCESSABLE_ENTITY),
        # Transporte HTTP (ClassificationReason via STOP_FAILURE)
        ("network_error", "network_error", http_status.HTTP_503_SERVICE_UNAVAILABLE),
        ("connection_error", "connection_error", http_status.HTTP_503_SERVICE_UNAVAILABLE),
        ("timeout", "timeout", http_status.HTTP_503_SERVICE_UNAVAILABLE),
        ("server_error", "server_error", http_status.HTTP_503_SERVICE_UNAVAILABLE),
        ("access_denied", "access_denied", http_status.HTTP_503_SERVICE_UNAVAILABLE),
        ("rate_limited", "rate_limited", http_status.HTTP_429_TOO_MANY_REQUESTS),
        ("client_error", "client_error", http_status.HTTP_422_UNPROCESSABLE_ENTITY),
        ("html_empty", "html_empty", http_status.HTTP_422_UNPROCESSABLE_ENTITY),
        # Browser
        ("playwright_timeout", "playwright_timeout", http_status.HTTP_504_GATEWAY_TIMEOUT),
        ("playwright_fetch_error", "playwright_fetch_error", http_status.HTTP_503_SERVICE_UNAVAILABLE),
        ("playwright_not_ready", "pipeline_degraded", http_status.HTTP_503_SERVICE_UNAVAILABLE),
        ("pipeline_degraded", "pipeline_degraded", http_status.HTTP_503_SERVICE_UNAVAILABLE),
        ("browser_fetch_failed", "browser_fetch_failed", http_status.HTTP_503_SERVICE_UNAVAILABLE),
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
        # Configuração
        "missing_proxy_config",
        # Anti-bot / rate limit
        "anti_bot_blocked",
        "anti_bot_page",
        "rate_limiter_cooldown",
        # URL
        "too_many_redirects",
        "invalid_url",
        # Transporte HTTP (ClassificationReason via STOP_FAILURE)
        "network_error",
        "connection_error",
        "timeout",
        "server_error",
        "access_denied",
        "rate_limited",
        "client_error",
        "html_empty",
        # Browser (Playwright)
        "playwright_timeout",
        "playwright_fetch_error",
        "playwright_not_ready",
        "pipeline_degraded",
        "browser_fetch_failed",
    }
    assert expected_codes == set(COLLECTION_ERROR_MAP.keys())


# ── CACHE_INVALIDATING_ERROR_CODES ───────────────────────────────────────────


def test_anti_bot_blocked_invalidates_cache():
    """anti_bot_blocked deve invalidar cache — bloqueio terminal vem do HTTP após Fase 1."""
    assert "anti_bot_blocked" in CACHE_INVALIDATING_ERROR_CODES


def test_anti_bot_page_invalidates_cache():
    """anti_bot_page (não-terminal) também invalida cache."""
    assert "anti_bot_page" in CACHE_INVALIDATING_ERROR_CODES


def test_transitoria_nao_invalida_cache():
    """Erros de infra transitória não devem invalidar cache."""
    assert "timeout" not in CACHE_INVALIDATING_ERROR_CODES
    assert "network_error" not in CACHE_INVALIDATING_ERROR_CODES
    assert "playwright_timeout" not in CACHE_INVALIDATING_ERROR_CODES


# ── HTTP_TIMEOUT_ORIGIN_OVERRIDES ────────────────────────────────────────────


def test_http_timeout_origin_overrides_contem_origens_semanticas():
    """Origens HTTP com causa conhecida devem estar no conjunto de override."""
    assert "server_error" in HTTP_TIMEOUT_ORIGIN_OVERRIDES
    assert "access_denied" in HTTP_TIMEOUT_ORIGIN_OVERRIDES
    assert "html_empty" in HTTP_TIMEOUT_ORIGIN_OVERRIDES
    assert "rate_limited" in HTTP_TIMEOUT_ORIGIN_OVERRIDES
    assert "anti_bot_page" in HTTP_TIMEOUT_ORIGIN_OVERRIDES


def test_http_timeout_origin_overrides_nao_contem_browser_errors():
    """Erros próprios do browser não devem estar no conjunto de override."""
    assert "playwright_timeout" not in HTTP_TIMEOUT_ORIGIN_OVERRIDES
    assert "playwright_fetch_error" not in HTTP_TIMEOUT_ORIGIN_OVERRIDES
    assert "browser_fetch_failed" not in HTTP_TIMEOUT_ORIGIN_OVERRIDES
