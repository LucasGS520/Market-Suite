""" Valida comportamento do cache em memória com LRU/TTL instrumentado """

from __future__ import annotations

import importlib
import time
from collections.abc import Callable

import pytest

from shared.metrics.metrics_scraper import (
    SCRAPER_CACHE_EVICTIONS_TOTAL,
    SCRAPER_CACHE_HIT_RATE,
    SCRAPER_CACHE_LOOKUPS_TOTAL,
    SCRAPER_CACHE_SIZE,
)


@pytest.fixture()
def cache_factory(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """ Recarrega o módulo de cache respeitando configs controladas nos testes """
    def _reload(ttl_seconds: int = 60, max_entries: int = 10) -> None:
        from market_scraper.core import config_scraper

        monkeypatch.setenv("SCRAPER_CACHE_TTL_SECONDS", str(ttl_seconds))
        monkeypatch.setenv("SCRAPER_CACHE_MAX_ENTRIES", str(max_entries))
        monkeypatch.setattr(config_scraper.settings, "SCRAPER_CACHE_TTL_SECONDS", ttl_seconds)
        monkeypatch.setattr(config_scraper.settings, "SCRAPER_CACHE_MAX_ENTRIES", max_entries)
        module = importlib.reload(importlib.import_module("market_scraper.utils.cache"))
        module.clear()
        SCRAPER_CACHE_SIZE.set(0)
        SCRAPER_CACHE_HIT_RATE.set(0)

    return _reload


def setup_function() -> None:
    """ Reseta métricas globais usadas no asserts de cada caso de teste """
    SCRAPER_CACHE_EVICTIONS_TOTAL.labels(reason="capacity")._value.set(0)
    SCRAPER_CACHE_EVICTIONS_TOTAL.labels(reason="expired")._value.set(0)
    SCRAPER_CACHE_LOOKUPS_TOTAL.labels(outcome="hit")._value.set(0)
    SCRAPER_CACHE_LOOKUPS_TOTAL.labels(outcome="miss")._value.set(0)

def test_set_and_get_return_value(cache_factory: Callable[[], None]) -> None:
    """ Confere se ``set`` seguido de ``get`` retorna o HTML armazenado """
    cache_factory()
    from market_scraper.utils import cache

    cache.set("https://exemplo.com/produto", "<html>...</html>", ttl_seconds=60)
    assert cache.get("https://exemplo.com/produto") == "<html>...</html>"
    assert SCRAPER_CACHE_HIT_RATE._value.get() == 1.0

def test_get_respects_ttl_expiration(cache_factory: Callable[[], None]) -> None:
    """ Garante que itens expiram naturalmente após o TTL configurado"""
    cache_factory(ttl_seconds=1)
    from market_scraper.utils import cache

    cache.set("https://exemplo.com/promo", "<html>promo</html>", ttl_seconds=1)
    time.sleep(1.1)

    assert cache.get("https://exemplo.com/promo") is None
    assert SCRAPER_CACHE_EVICTIONS_TOTAL.labels(reason="expired")._value.get() == 1.0
    assert SCRAPER_CACHE_SIZE._value.get() == 0.0

def test_get_updates_metrics_when_multiple_entries_expire(cache_factory: Callable[[], None]) -> None:
    """ Confirma contagem correta de TTL ao expirar vários itens simultaneamente """
    cache_factory(ttl_seconds=1)
    from market_scraper.utils import cache

    cache.set("https://exemplo.com/ttl1", "<html>1</html>", ttl_seconds=1)
    cache.set("https://exemplo.com/ttl2", "<html>2</html>", ttl_seconds=1)
    time.sleep(1.1)

    assert cache.get("https://exemplo.com/ttl1") is None
    assert SCRAPER_CACHE_EVICTIONS_TOTAL.labels(reason="expired")._value.get() == 2.0
    assert SCRAPER_CACHE_SIZE._value.get() == 0.0

def test_set_accepts_custom_ttl(cache_factory: Callable[[], None]) -> None:
    """ Confirma que cada escrita pode definir TTL menor que o padrão global """
    cache_factory(ttl_seconds=60)
    from market_scraper.utils import cache

    cache.set("https://exemplo.com/custom", "<html>custom</html>", ttl_seconds=1)
    time.sleep(1.1)

    assert cache.get("https://exemplo.com/custom") is None

def test_set_updates_metrics_when_expired_entries_are_cleaned(
    cache_factory: Callable[[], None]
) -> None:
    """ Garante que ``set`` registra remoções de TTL anteriores à nova escrita """
    cache_factory(ttl_seconds=1)
    from market_scraper.utils import cache

    cache.set("https://exemplo.com/antigo", "<html>antigo</html>", ttl_seconds=1)
    time.sleep(1.1)

    cache.set("https://exemplo.com/novo", "<html>novo</html>", ttl_seconds=60)

    assert SCRAPER_CACHE_EVICTIONS_TOTAL.labels(reason="expired")._value.get() == 1.0
    assert SCRAPER_CACHE_SIZE._value.get() == 1.0

def test_invalidate_removes_entry(cache_factory: Callable[[], None]) -> None:
    """ Assegura que ``invalidate`` elimina itens específicos do cache """
    cache_factory()
    from market_scraper.utils import cache

    cache.set("https://exemplo.com/item", "<html>item</html>", ttl_seconds=30)
    cache.invalidate("https://exemplo.com/item")
    assert cache.get("https://exemplo.com/item") is None
    
def test_capacity_eviction_updates_metric(cache_factory: Callable[[], None]) -> None:
    """ Valida que excesso de itens dispara eviction LRU e métrica dedicada """
    cache_factory(max_entries=2)
    from market_scraper.utils import cache

    cache.set("https://exemplo.com/a", "<html>a</html>", ttl_seconds=60)
    cache.set("https://exemplo.com/b", "<html>b</html>", ttl_seconds=60)
    cache.set("https://exemplo.com/c", "<html>c</html>", ttl_seconds=60)

    assert SCRAPER_CACHE_EVICTIONS_TOTAL.labels(reason="capacity")._value.get() == 1.0
    assert SCRAPER_CACHE_SIZE._value.get() == 2.0

def test_hit_rate_metric_tracks_hits_and_misses(cache_factory: Callable[[], None]) -> None:
    """ Confirma cálculo de taxa de acerto a partir de hits e misses """
    cache_factory()
    from market_scraper.utils import cache

    cache.set("https://exemplo.com/acerto", "<html>ok</html>", ttl_seconds=60)
    assert cache.get("https://exemplo.com/acerto") == "<html>ok</html>"
    assert cache.get("https://exemplo.com/erro") is None

    assert SCRAPER_CACHE_HIT_RATE._value.get() == pytest.approx(0.5)

def test_clear_resets_metrics_and_restarts_hit_rate(cache_factory: Callable[[], None]) -> None:
    """ Valida reinicialização completa de métricas após limpeza manual """
    cache_factory()
    from market_scraper.utils import cache

    cache.set("https://exemplo.com/hit", "<html>hit</html>", ttl_seconds=60)
    assert cache.get("https://exemplo.com/hit") == "<html>hit</html>"
    assert cache.get("https://exemplo.com/miss") is None

    assert SCRAPER_CACHE_HIT_RATE._value.get() == pytest.approx(0.5)

    cache.clear()

    assert SCRAPER_CACHE_SIZE._value.get() == 0.0
    assert SCRAPER_CACHE_HIT_RATE._value.get() == 0.0

    cache.set("https://exemplo.com/novo", "<html>novo</html>", ttl_seconds=60)
    assert cache.get("https://exemplo.com/novo") == "<html>novo</html>"

    assert SCRAPER_CACHE_HIT_RATE._value.get() == 1.0
