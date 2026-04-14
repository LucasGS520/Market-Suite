from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import BaseModel, ValidationError

from shared.utils.exception_sanitization import sanitize_exception_message
from shared.utils.http_headers import normalize_headers, parse_http_datetime
from shared.utils.scraper_response_normalizer import normalize_scraper_response
from shared.utils.text_sanitization import sanitize_media_url, sanitize_text
from shared.utils.trace_context import (
    clear_trace_id,
    get_or_create_trace_id,
    get_trace_id,
    set_trace_id,
)
from shared.utils.url_validation import (
    UrlIssue,
    canonicalize_product_url,
    check_url_compatibility,
    normalize_and_validate_product_url,
    normalize_competitor_url,
    normalize_product_url,
    normalize_product_url_for_storage,
)


pytestmark = pytest.mark.unit


class _PayloadModel(BaseModel):
    name: str
    current_price: str | None = None
    source: str | None = None


def test_url_validation_normalizes_and_canonicalizes_product_urls():
    normalized = normalize_product_url(" example.com/product/?a=1#frag ")
    canonical = canonicalize_product_url("https://www.Example.com:443//product/?a=1#frag")
    validated, issue = normalize_and_validate_product_url("https://example.com/item/")

    assert normalized == "https://example.com/product/?a=1"
    assert canonical == "https://example.com/product"
    assert validated == "https://example.com/item"
    assert issue is None


def test_url_validation_reports_invalid_cases_and_storage_fallbacks():
    with pytest.raises(ValueError, match="HTTP ou HTTPS"):
        normalize_product_url("ftp://example.com/file")

    with pytest.raises(ValueError, match="Credenciais"):
        normalize_product_url("https://user:secret@example.com/item")

    issue = check_url_compatibility(
        "https://example.com/item",
        ensure_public_endpoint=lambda host: UrlIssue("private_host", f"{host} blocked"),
    )

    assert issue == UrlIssue(code="private_host", message="example.com blocked")
    assert normalize_product_url_for_storage("  ") == ""
    assert normalize_competitor_url("ftp://legacy.example.com/item") == "ftp://legacy.example.com/item"


def test_text_and_media_sanitization_remove_unsafe_content():
    assert sanitize_text(" <b>Oferta</b>\x00 ") == "Oferta"
    assert sanitize_text("   ") is None
    assert sanitize_media_url("https://cdn.example.com/image.png#frag") == "https://cdn.example.com/image.png"
    assert sanitize_media_url("javascript:alert(1)") is None


def test_http_header_helpers_normalize_case_and_parse_dates():
    parsed = parse_http_datetime("Wed, 21 Oct 2015 07:28:00 GMT")
    naive = parse_http_datetime("Wed, 21 Oct 2015 07:28:00")

    assert normalize_headers({"ETag": "abc", "Last-Modified": "x"}) == {
        "etag": "abc",
        "last-modified": "x",
    }
    assert parsed == datetime(2015, 10, 21, 7, 28, tzinfo=timezone.utc)
    assert naive == datetime(2015, 10, 21, 7, 28, tzinfo=timezone.utc)
    assert parse_http_datetime("not-a-date") is None


def test_trace_context_creates_sets_and_clears_trace_id():
    clear_trace_id()
    generated = get_or_create_trace_id()

    assert generated == get_trace_id()

    set_trace_id("trace-123")
    assert get_trace_id() == "trace-123"

    clear_trace_id()
    assert get_trace_id() is None


def test_sanitize_exception_message_masks_secrets_and_truncates():
    message = (
        "user=john@example.com bearer eyJabc1234567890.tokenpayload.signature "
        "password=super-secret"
    )
    sanitized = sanitize_exception_message(message, max_length=40)

    assert "[REDACTED]" in sanitized
    assert "john@example.com" not in sanitized
    assert "super-secret" not in sanitized
    assert sanitized.endswith("...[TRUNCATED]")


def test_normalize_scraper_response_accepts_supported_payload_types():
    model_payload = _PayloadModel(name="Produto", current_price="10.00", source="example")
    dict_payload = {"name": "Produto", "source": "example"}
    json_payload = '{"name":"Produto","source":"example"}'

    normalized_model = normalize_scraper_response(model_payload, source="unit-test")
    normalized_dict = normalize_scraper_response(dict_payload, source="unit-test")
    normalized_json = normalize_scraper_response(json_payload, source="unit-test")

    assert normalized_model.name == "Produto"
    assert str(normalized_model.current_price) == "10.00"
    assert normalized_dict.source == "example"
    assert normalized_json.source == "example"

    with pytest.raises(ValidationError):
        normalize_scraper_response('{"url":"notaurl"}', source="unit-test")
