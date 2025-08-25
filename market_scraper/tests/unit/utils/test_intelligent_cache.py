""" Testes para o ``IntelligentCacheManager`` """

from market_scraper.utils.intelligent_cache import IntelligentCacheManager


def test_cache_isolado_por_marketplace() -> None:
    """ Verifica se URLs iguais em marketplaces diferentes não coliidem """
    cache = IntelligentCacheManager()
    url = "https://site.com/produto"
    dado_ml = {"name": "Produto ML"}
    dado_amz = {"name": "Produto AMZ"}

    cache.set(marketplace="mercadolivre.com", url=url, value=dado_ml)
    cache.set(marketplace="amazon.com", url=url, value=dado_amz)

    assert cache.get(marketplace="mercadolivre.com", url=url)["name"] == "Produto ML"
    assert cache.get(marketplace="amazon.com", url=url)["name"] == "Produto AMZ"
