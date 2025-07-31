from app.utils.intelligent_cache import IntelligentCacheManager

def test_intelligent_cache_set_get_performance(benchmark, patch_rate_limiter):
    cache = IntelligentCacheManager(base_ttl=10, max_multiplier=3)
    url = "https://example.com/item"
    data = {"current_price": "1"}
    html = "<html></html>"

    def action():
        cache.set(url, data, html)
        cache.get_data(url)

    benchmark(action)
