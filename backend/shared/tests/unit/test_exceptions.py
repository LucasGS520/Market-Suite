from __future__ import annotations

import pytest

from shared.exceptions import ScraperError, TemporalConnectionError, TemporalUnavailableError


pytestmark = pytest.mark.unit


def test_temporal_connection_error_preserves_context_in_str():
    error = TemporalConnectionError(
        "Temporal indisponivel",
        attempts=3,
        target="localhost:7233",
    )

    assert error.attempts == 3
    assert error.target == "localhost:7233"
    assert "attempts=3" in str(error)
    assert "localhost:7233" in str(error)


def test_temporal_unavailable_error_is_regular_exception():
    error = TemporalUnavailableError("temporarily down")

    assert isinstance(error, Exception)
    assert str(error) == "temporarily down"


def test_scraper_error_is_serializable_for_celery():
    error = ScraperError(503, "timeout")
    reducer = error.__reduce__()

    assert error.status_code == 503
    assert error.detail == "timeout"
    assert str(error) == "503: timeout"
    assert reducer == (ScraperError, (503, "timeout"))
