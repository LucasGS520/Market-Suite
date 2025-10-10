""" Garante funcionamento básico do cache em memória do scraper """

from __future__ import annotations

import time

from market_scraper.utils import cache


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
    