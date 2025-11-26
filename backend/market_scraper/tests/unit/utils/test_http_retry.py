""" Testes para garantir que o retry HTTP interprete ``Retry-After`` corretamente """

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from market_scraper.utils.http_retry import (
    RetryableHTTPError,
    _raise_for_retryable_response,
)


def _build_response(*, status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    """Cria resposta sintética com request associado para facilitar asserts"""
    request = httpx.Request("GET", "https://example.com")
    return httpx.Response(status_code, headers=headers or {}, request=request)


def test_raise_for_retryable_response_fractional_retry_after() -> None:
    response = _build_response(status_code=429, headers={"Retry-After": "1.5"})

    with pytest.raises(RetryableHTTPError) as exc_info:
        _raise_for_retryable_response(response, target="html")

    assert exc_info.value.retry_after == pytest.approx(1.5)


def test_raise_for_retryable_response_http_date_retry_after() -> None:
    future = datetime.now(timezone.utc) + timedelta(seconds=5)
    header = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
    response = _build_response(status_code=503, headers={"Retry-After": header})

    with pytest.raises(RetryableHTTPError) as exc_info:
        _raise_for_retryable_response(response, target="html")

    retry_after = exc_info.value.retry_after
    assert retry_after is not None
    assert retry_after == pytest.approx(5.0, rel=0.2)


def test_raise_for_retryable_response_invalid_retry_after_defaults_to_none() -> None:
    response = _build_response(status_code=502, headers={"Retry-After": "invalid"})

    with pytest.raises(RetryableHTTPError) as exc_info:
        _raise_for_retryable_response(response, target="html")

    assert exc_info.value.retry_after is None
