import asyncio
import pytest

from market_scraper.services import services_cache_scraper as cache


@pytest.mark.asyncio
async def test_set_cached_html_stores_in_memory_and_redis(monkeypatch, fake_redis):
    def setex(key, ttl, value):
        fake_redis.set(key, value, ex=ttl)

    fake_redis.setex = setex
    monkeypatch.setattr(cache, "get_redis_client", lambda: fake_redis)
    with cache.cache_lock:
        cache._cache.clear()

    url = "https://exemplo.com/produto"
    html = "<html>produto</html>"

    await cache.set_cached_html(url, html, ttl=100)

    redis_key = f"scraper:html:{url}"
    assert fake_redis.get(redis_key) == html
    assert fake_redis.data[f"ttl:{redis_key}"] == 100
    with cache.cache_lock:
        assert cache._cache[url]["html"] == html

@pytest.mark.asyncio
async def test_get_cached_html_from_redis(monkeypatch, fake_redis):
    def setex(key, ttl, value):
        fake_redis.set(key, value, ex=ttl)

    fake_redis.setex = setex
    monkeypatch.setattr(cache, "get_redis_client", lambda: fake_redis)
    with cache.cache_lock:
        cache._cache.clear()

    url = "https://exemplo.com/produto"
    html = "<html>produto</html>"
    await cache.set_cached_html(url, html)

    assert await cache.get_cached_html(url) == html

@pytest.mark.asyncio
async def test_get_cached_html_fallback_local(monkeypatch):
    class BrokenRedis:
        def get(self, key):
            raise Exception("indisponivel")

    monkeypatch.setattr(cache, "get_redis_client", lambda: BrokenRedis())
    with cache.cache_lock:
        cache._cache.clear()
    url = "https://exemplo.com/produto"
    with cache.cache_lock:
        cache._cache[url] = {"html": "<html>velho</html>", "timestamp": -400}

    assert await cache.get_cached_html(url, max_age=300) is None

@pytest.mark.asyncio
async def test_set_cached_html_redis_falha_ainda_persiste_local(monkeypatch):
    class BrokenRedis:
        def setex(self, *a, **k):
            raise Exception("indisponível")

    monkeypatch.setattr(cache, "get_redis_client", lambda: BrokenRedis())
    with cache.cache_lock:
        cache._cache.clear()

    url = "https://exemplo.com/produto"
    html = "<html>produto</html>"

    await cache.set_cached_html(url, html, ttl=100)

    with cache.cache_lock:
        assert cache._cache[url]["html"] == html

@pytest.mark.asyncio
async def test_concurrent_access_to_local_cache(monkeypatch):
    #Força uso apenas do cache local
    monkeypatch.setattr(cache, "get_redis_client", lambda: None)
    with cache.cache_lock:
        cache._cache.clear()

    url = "https://exemplo.com/produto"
    html = "<html>produto</html>"

    async def writer():
        await cache.set_cached_html(url, html)

    async def reader():
        return await cache.get_cached_html(url)

    #Executa leituras e escritas de forma concorrente
    tasks = [asyncio.create_task(writer()) for _ in range(5)]
    tasks += [asyncio.create_task(reader()) for _ in range(5)]

    results = await asyncio.gather(*tasks)

    with cache.cache_lock:
        assert cache._cache[url]["html"] == html

    #Ao menos uma leitura deve ter retornado o HTML esperado
    assert html in results
