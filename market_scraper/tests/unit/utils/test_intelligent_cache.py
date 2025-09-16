""" Testes para o ``IntelligentCacheManager`` """

from market_scraper.utils.intelligent_cache import IntelligentCacheManager


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
    