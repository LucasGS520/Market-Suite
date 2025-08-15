import pytest

from market_scraper.services import services_cache_scraper as cache


def test_set_cached_html_stores_in_memory_and_redis(monkeypatch, fake_redis):
    def setex(key, ttl, value):
        fake_redis.set(key, value, ex=ttl)

    fake_redis.setex = setex
    monkeypatch.setattr(cache, "get_redis_client", lambda: fake_redis)
    cache._cache.clear()

    url = "https://exemplo.com/produto"
    html = "<html>produto</html>"

    cache.set_cached_html(url, html, ttl=100)

    redis_key = f"scraper:html:{url}"
    assert fake_redis.get(redis_key) == html
    assert fake_redis.data[f"ttl:{redis_key}"] == 100
    assert cache._cache[url]["html"] == html

def test_get_cached_html_from_redis(monkeypatch, fake_redis):
    def setex(key, ttl, value):
        fake_redis.set(key, value, ex=ttl)

    fake_redis.setex = setex
    monkeypatch.setattr(cache, "get_redis_client", lambda: fake_redis)
    cache._cache.clear()

    url = "https://exemplo.com/produto"
    html = "<html>produto</html>"
    cache.set_cached_html(url, html)

    assert cache.get_cached_html(url) == html

def test_get_cached_html_fallback_local(monkeypatch):
    class BrokenRedis:
        def get(self, key):
            raise Exception("indisponivel")

    monkeypatch.setattr(cache, "get_redis_client", lambda: BrokenRedis())
    cache._cache.clear()
    url = "https://exemplo.com/produto"
    cache._cache[url] = {"html": "<html>velho</html>", "timestamp": -400}

    assert cache.get_cached_html(url, max_age=300) is None
