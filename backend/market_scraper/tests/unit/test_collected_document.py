"""Testes unitários para CollectedDocument e CollectionAttempt DTOs."""

from __future__ import annotations

import time

from market_scraper.collection.dto.collected_document import CollectedDocument
from market_scraper.collection.dto.collection_attempt import CollectionAttempt


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_document(**overrides) -> CollectedDocument:
    defaults = dict(
        html="<html>" + "x" * 2000 + "</html>",
        http_status=200,
        headers={},
        layer_used="http",
        fallback_taken=False,
        anti_bot_detected=False,
        anti_bot_pattern=None,
        timestamp=time.time(),
        duration_ms=120.0,
        attempts=(),
    )
    defaults.update(overrides)
    return CollectedDocument(**defaults)


def _make_attempt(**overrides) -> CollectionAttempt:
    defaults = dict(
        layer="http",
        status="success",
        error_code=None,
        duration_ms=100.0,
        reason="html_ok",
    )
    defaults.update(overrides)
    return CollectionAttempt(**defaults)


# ── CollectionAttempt ─────────────────────────────────────────────────────────

def test_attempt_is_frozen():
    attempt = _make_attempt()
    try:
        attempt.layer = "browser"  # type: ignore[misc]
        assert False, "deveria ter levantado FrozenInstanceError"
    except Exception:
        pass


def test_attempt_fields_stored_correctly():
    attempt = CollectionAttempt(
        layer="browser",
        status="failure",
        error_code="timeout",
        duration_ms=500.5,
        reason="browser_timeout",
    )
    assert attempt.layer == "browser"
    assert attempt.status == "failure"
    assert attempt.error_code == "timeout"
    assert attempt.duration_ms == 500.5
    assert attempt.reason == "browser_timeout"


# ── CollectedDocument.is_successful ──────────────────────────────────────────

def test_is_successful_with_valid_html():
    doc = _make_document(html="<html>content</html>")
    assert doc.is_successful is True


def test_is_successful_false_when_html_none():
    doc = _make_document(html=None)
    assert doc.is_successful is False


def test_is_successful_false_when_html_whitespace_only():
    doc = _make_document(html="   \n\t  ")
    assert doc.is_successful is False


# ── CollectedDocument.data_quality ───────────────────────────────────────────

def test_data_quality_normal():
    doc = _make_document(fallback_taken=False, anti_bot_detected=False)
    assert doc.data_quality == "normal"


def test_data_quality_browser_fallback_takes_precedence():
    doc = _make_document(fallback_taken=True, anti_bot_detected=True)
    assert doc.data_quality == "browser_fallback"


def test_data_quality_degraded_anti_bot():
    doc = _make_document(fallback_taken=False, anti_bot_detected=True, anti_bot_pattern="cloudflare_challenge")
    assert doc.data_quality == "degraded_anti_bot"


# ── CollectedDocument é imutável ──────────────────────────────────────────────

def test_document_is_frozen():
    doc = _make_document()
    try:
        doc.html = "other"  # type: ignore[misc]
        assert False, "deveria ter levantado FrozenInstanceError"
    except Exception:
        pass


# ── Tentativas integradas ─────────────────────────────────────────────────────

def test_document_stores_multiple_attempts():
    attempts = (
        _make_attempt(layer="http", status="escalated"),
        _make_attempt(layer="browser", status="success"),
    )
    doc = _make_document(attempts=attempts)
    assert len(doc.attempts) == 2
    assert doc.attempts[0].layer == "http"
    assert doc.attempts[1].layer == "browser"
