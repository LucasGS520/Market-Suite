""" Garante funcionamento básico do cache em memória do scraper """

from __future__ import annotations

import time

from market_scraper.utils import cache
from shared.metrics.metrics_scraper import SCRAPER_CACHE_SIZE


def setup_function() -> None:
    """ Limpa cache entre testes para evitar interferências cruzadas """
    cache.clear()

def test_set_and_get_return_value() -> None:
    """ Confere se ``set`` seguido de ``get`` retorna HTML salvo """
    cache.set("https://exemplo.com/produto", "<html>...</html>", ttl_seconds=30)
    assert cache.get("https://exemplo.com/produto") == "<html>...</html>"

def test_get_respects_ttl_expiration() -> None:
    """ Valida que itens expiram após o TTL informado """
    cache.set("https://exemplo.com/promo", "<html>promo</html>", ttl_seconds=1)
    time.sleep(1.1)
    #Aguarda ligeiramente acima do TTL garantindo expiração natural
    assert cache.get("https://exemplo.com/promo") is None

def test_invalidate_removes_entry() -> None:
    """ Assegura que ``invalidate`` elimina itens específicos do cache """
    cache.set("https://exemplo.com/item", "<html>item</html>", ttl_seconds=30)
    cache.invalidate("https://exemplo.com/item")
    assert cache.get("https://exemplo.com/item") is None
    
def test_set_triggers_cleanup_for_expired_entries() -> None:
    """ Garante que ``set`` descarta itens expirados e atualiza gauge """
    urls = [f"https://exemplo.com/pagina-{idx}" for idx in range(3)]
    for url in urls:
        cache.set(url, "<html>conteudo</html>", ttl_seconds=1)

    time.sleep(1.1)

    #Ajustamos o intervalo para zero garantindo que a próxima escrita dispare a limpeza
    old_interval = cache._CACHE._cleanup_interval_seconds
    old_last_cleanup = cache._CACHE._last_cleanup

    cache._CACHE._cleanup_interval_seconds = 0
    cache._CACHE._last_cleanup = 0

    try:
        cache.set("https://exemplo.com/novo", "<html>novo</html>", ttl_seconds=30)

        assert list(cache._CACHE._data.keys()) == ["https://exemplo.com/novo"]
        assert SCRAPER_CACHE_SIZE._value.get() == 1.0
    finally:
        cache._CACHE._cleanup_interval_seconds = old_interval
        cache._CACHE._last_cleanup = old_last_cleanup
        