""" Testes para o ``IntelligentCacheManager`` """

from shared.metrics.metrics_scraper import (
    SCRAPER_CACHE_LATENCY_SECONDS,
    SCRAPER_CACHE_LOCAL_SIZE,
    SCRAPER_CACHE_LOOKUPS_TOTAL,
)

from market_scraper.utils.intelligent_cache import IntelligentCacheManager

def _hist_count(metric, **labels) -> float:
    """ Recupera a contagem observada para um histograma """
    child = metric.labels(**labels)
    for sample in child._samples():
        if sample.name == "_count":
            return sample.value
    return AssertionError("Contagem não encontrada")

def test_cache_isolado_por_marketplace() -> None:
    """ Verifica se URLs iguais em marketplaces diferentes não colidem """
    cache = IntelligentCacheManager()
    url = "https://site.com/produto"
    dado_ml = {"name": "Produto ML"}
    dado_amz = {"name": "Produto AMZ"}

    cache.set(marketplace="mercadolivre.com.br", url=url, value=dado_ml)
    cache.set(marketplace="amazon.com", url=url, value=dado_amz)

    assert cache.get(marketplace="mercadolivre.com.br", url=url)["name"] == "Produto ML"
    assert cache.get(marketplace="amazon.com", url=url)["name"] == "Produto AMZ"

def test_touch_atualiza_ttl_local() -> None:
    """ Garante que o método ``touch`` renova o timestamp do cache em memória """
    cache = IntelligentCacheManager(ttl=1)
    url = "https://site.com/produto"
    valor = {"name": "Produto"}

    cache.set(marketplace="site.com", url=url, value=valor)
    key = next(iter(cache._local_cache))
    cache._local_cache[key]["timestamp"] -= 10

    cache.touch(marketplace="site.com", url=url)
    assert cache.get(marketplace="site.com", url=url) == valor
    
def test_metricas_cache_monitoram_hits_e_expiracao(monkeypatch) -> None:
    """ Confere que hits, misses e expirações atualizam as métricas """
    monkeypatch.setattr(
        "market_scraper.utils.intelligent_cache.get_redis_client",
        lambda: None,
    )
    cache = IntelligentCacheManager(ttl=1)
    url = "https://dominio.com/produto"
    valor = {"name": "Produto"}

    redis_unavailable_before = SCRAPER_CACHE_LOOKUPS_TOTAL.labels(
        backend="redis", outcome="unavailable"
    )._value.get()
    local_miss_before = SCRAPER_CACHE_LOOKUPS_TOTAL.labels(
        backend="local", outcome="miss"
    )._value.get()
    local_hit_before = SCRAPER_CACHE_LOOKUPS_TOTAL.labels(
        backend="local", outcome="hit"
    )._value.get()
    local_expired_before = SCRAPER_CACHE_LOOKUPS_TOTAL.labels(
        backend="local", outcome="expired"
    )._value.get()

    get_count_before = _hist_count(SCRAPER_CACHE_LATENCY_SECONDS, operation="get")

    assert cache.get(marketplace="dominio.com", url=url) is None

    assert _hist_count(SCRAPER_CACHE_LATENCY_SECONDS, operation="get") == get_count_before + 1
    assert (
        SCRAPER_CACHE_LOOKUPS_TOTAL.labels(backend="redis", outcome="unavailable")._value.get() == redis_unavailable_before + 1
    )
    assert _hist_count(SCRAPER_CACHE_LATENCY_SECONDS, operation="get") == get_count_before + 2

    size_after_hit = SCRAPER_CACHE_LOCAL_SIZE._value.get()
    assert size_after_hit >= 1

    #Força expiração do cache local
    for entry in cache._local_cache.values():
        entry["timestamp"] -= 5

    assert cache.get(marketplace="dominio.com", url=url) is None
    assert (
        SCRAPER_CACHE_LOOKUPS_TOTAL.labels(backend="local", outcome="expired")._value.get() == local_expired_before + 1
    )
    assert (
        SCRAPER_CACHE_LOOKUPS_TOTAL.labels(backend="redis", outcome="unavailable")._value.get() == redis_unavailable_before + 3
    )
    assert SCRAPER_CACHE_LOCAL_SIZE._value.get() == 0

    touch_count_before = _hist_count(SCRAPER_CACHE_LATENCY_SECONDS, operation="touch")
    cache.touch(marketplace="dominio.com", url=url)
    assert _hist_count(SCRAPER_CACHE_LATENCY_SECONDS, operation="touch") == touch_count_before + 1
    