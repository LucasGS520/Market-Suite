from types import SimpleNamespace

import scraper_app.services.services_cache_scraper as cache_scraper
from scraper_app.services.services_cache_scraper import use_cache_if_not_modified, update_cache

def _html():
    return "<html></html>"

def _payload():
    return SimpleNamespace(model_dump=lambda: {"foo": "bar"})

class DummyCB:
    def __init__(self):
        self.called = None

    def record_success(self, key):
        self.called = key

def test_use_cache_returns_cached_data(monkeypatch):
    html = _html()
    hash_val = cache_scraper.cache_manager._hash_content(html)
    cached = {"data": {"v": 1}, "hash": hash_val}
    monkeypatch.setattr(cache_scraper.cache_manager, "get", lambda url: cached)
    monkeypatch.setattr(cache_scraper, "audit_scrape", lambda *a, **k: None)
    cb = DummyCB()

    result = use_cache_if_not_modified(
        target_url="http://example.com",
        html=html,
        payload=_payload(),
        circuit_breaker=cb,
        circuit_key="c",
    )

    assert cb.called == "c"
    assert result == {"status": "cached", "details": cached["data"]}

def test_use_cache_returns_none_when_cache_empty(monkeypatch):
    html = _html()
    monkeypatch.setattr(cache_scraper.cache_manager, "get", lambda url: None)
    monkeypatch.setattr(cache_scraper, "audit_scrape", lambda *a, **k: None)
    cb = DummyCB()

    result = use_cache_if_not_modified(
        target_url="http://example.com",
        html=html,
        payload=_payload(),
        circuit_breaker=cb,
        circuit_key="c",
    )
    assert result is None
    assert cb.called is None

def test_use_cache_returns_none_with_other_hash(monkeypatch):
    html = _html()
    cached = {"data": {"ok": True}, "hash": "different"}
    monkeypatch.setattr(cache_scraper.cache_manager, "get", lambda url: cached)
    cb = DummyCB()
    result = use_cache_if_not_modified(
        target_url="http://example.com",
        html=html,
        payload=_payload(),
        circuit_breaker=cb,
        circuit_key="c",
    )
    assert result is None
    assert cb.called is None

def test_update_cache_stores(monkeypatch):
    captured = {}

    def fake_set(url, data, html, etag=None):
        captured.update(dict(url=url, data=data, html=html, etag=etag))

    monkeypatch.setattr(cache_scraper.cache_manager, "set", fake_set)
    update_cache("http://example.com", {"x": 1}, "<html></html>", "tag")
    assert captured == {
        "url": "http://example.com",
        "data": {"x": 1},
        "html": "<html></html>",
        "etag": "tag",
    }
