""" Testes para utilitários de cache HTTP """

import pytest

from market_scraper.utils.http_cache import store_cache_headers, get_cache_headers, ContentSignature


def test_store_and_retrieve_headers(fake_redis):
    url = "https://example.com/produto"
    store_cache_headers(
        url, etag="etag123", last_modified="Mon, 01 Jan 2024 00:00:00 GMT"
    )
    headers = get_cache_headers(url)
    assert headers["etag"] == "etag123"
    assert headers["last_modified"] == "Mon, 01 Jan 2024 00:00:00 GMT"

def test_content_signature_detection(fake_redis):
    url = "https://example.com/produto"
    html_a = "<html>A</html>"
    html_b = "<html>B</html>"

    signer = ContentSignature(url)

    assert signer.has_changed(html_a) is True
    assert signer.has_changed(html_a) is False
    assert signer.has_changed(html_b) is True
    assert signer.get() == signer.calculate(html_b)

def test_cache_headers_expiration(fake_redis):
    url = "https://example.com/expira"
    store_cache_headers(
        url,
        etag="e1",
        last_modified="Mon, 01 Jan 2024 00:00:00 GMT",
        ttl_seconds=60,
    )
    fake_redis.advance_time(61)
    headers = get_cache_headers(url)
    assert headers["etag"] is None
    assert headers["last_modified"] is None
