from scraper_app.utils.intelligent_cache import IntelligentCacheManager

def test_adaptive_ttl_and_retrieval(patch_rate_limiter):
    cache = IntelligentCacheManager(base_ttl=10, max_multiplier=3)
    fake_redis = patch_rate_limiter
    url = "https://example.com/item"

    cache.set(url, {"current_price": "1"}, "<html>v1</html>")
    stored = cache.get_data(url)
    assert stored == {"current_price": "1"}
    ttl1 = fake_redis.data[f"ttl:{cache._key(url)}"]

    cache.set(url, {"current_price": 1}, "<html>v1</html>")
    ttl2 = fake_redis.data[f"ttl:{cache._key(url)}"]
    assert ttl2 == ttl1 * 2

    cache.set(url, {"current_price": "2"}, "<html>v2</html>")
    ttl3 = fake_redis.data[f"ttl:{cache._key(url)}"]
    assert ttl3 == cache.base_ttl
