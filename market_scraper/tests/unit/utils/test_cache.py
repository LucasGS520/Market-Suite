""" Valida comportamento do cache em memória com LRU/TTL instrumentado """

from __future__ import annotations

import importlib
import time
from collections.abc import Callable
from types import SimpleNamespace

import pytest
import redis

from shared.metrics.metrics_scraper import (
    SCRAPER_CACHE_EVICTIONS_TOTAL,
    SCRAPER_CACHE_HIT_RATE,
    SCRAPER_CACHE_LOOKUPS_TOTAL,
    SCRAPER_CACHE_REDIS_ERRORS_TOTAL,
    SCRAPER_CACHE_SIZE,
)

class DummyRedis:
    """ Simula clente Redis básico usando etruturas em memória para testes """
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}

    def pipeline(self) -> "_DummyPipeline":
        """ Retorna pipeline que executa comandos sequencialmente em memória """
        return _DummyPipeline(self)

    def get(self, key: str) -> str | None:
        """ Obtém valor armazenado, sem simular expiração automática """
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """ Armazena valor ignorando TTL (controlado externamente nos testes) """
        if ex == 0:
            self.store.pop(key, None)
            return True
        self.store[key] = value
        return True

    def delete(self, *keys: str) -> int:
        """ Remove chaves informadas, retornando quantidade deletada """
        removed = 0
        for key in keys:
            if self.store.pop(key, None) is not None:
                removed += 1
        return removed

    def sadd(self, index: str, member: str) -> int:
        """ Adiciona membro ao conjunto de índice auxiliar """
        self.sets.setdefault(index, set()).add(member)
        return 1

    def srem(self, index: str, member: str) -> int:
        """ Remove membro do conjunto de índice auxiliar """
        self.sets.setdefault(index, set()).discard(member)
        return 1

    def scard(self, index: str) -> int:
        """ Retorna cardinalidade atual do conjunto de índice auxiliar """
        return len(self.sets.get(index, set()))

    def smembers(self, index: str) -> set[str]:
        """ Lista membros registrados no índice auxiliar """
        return set(self.sets.get(index, set()))
    
class _DummyPipeline:
    """ Executa comandos acumulados respeitando a ordem de inserção """
    def __init__(self, client: _DummyRedis) -> None:
        self._client = client
        self._commands: list[tuple[str, tuple[object, ...]]] = []

    def set(self, key: str, value: str, ex: int) -> "_DummyPipeline":
        """ Enfileira operação ``SET`` com TTL opcional """
        self._commands.append(("set", (key, value, ex)))
        return self

    def sadd(self, index: str, member: str) -> "_DummyPipeline":
        """ Enfileira operação ``SADD`` para o índice auxiliar """
        self._commands.append(("sadd", (index, member)))
        return self

    def execute(self) -> list[bool]:
        """ Executa comandos armazenados utilizando o cliente associado """
        results: list[bool] = []
        for command, args in self._commands:
            match command:
                case "set":
                    key, value, ex = args
                    results.append(self._client.set(key, value, ex=ex))
                case "sadd":
                    index, member = args
                    self._client.sadd(index, member)
                    results.append(True)
        self._commands.clear()
        return results

@pytest.fixture()
def cache_factory(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """ Recarrega módulo de cache respeitando configs controladas nos testes """
    def _reload(
        ttl_seconds: int = 60, 
        max_entries: int = 10,
        backend: str = "memory",
    ) -> None:
        from market_scraper.core import config_scraper

        monkeypatch.setenv("SCRAPER_CACHE_BACKEND", backend)
        monkeypatch.setenv("SCRAPER_CACHE_TTL_SECONDS", str(ttl_seconds))
        monkeypatch.setenv("SCRAPER_CACHE_MAX_ENTRIES", str(max_entries))
        monkeypatch.setattr(config_scraper.settings, "SCRAPER_CACHE_BACKEND", backend)
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
    for operation in [
        "get",
        "set",
        "delete",
        "srem",
        "scard",
        "smembers",
        "delete_index",
    ]:
        SCRAPER_CACHE_REDIS_ERRORS_TOTAL.labels(operation=operation)._value.set(0)

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
    
def test_redis_backend_store_and_retrieve(monkeypatch: pytest.MonkeyPatch, cache_factory: Callable[..., None]) -> None:
    """ Garante que adapter Redis armazena dados e atualiza métricas principais """
    dummy_client = _DummyRedis()

    def _fake_from_url(*_: object, **__: object) -> SimpleNamespace:
        return SimpleNamespace(client=dummy_client)

    def _fake_redis(*args: object, **kwargs: object) -> _DummyRedis:
        connection_pool = kwargs.get("connection_pool") or args[0]
        return connection_pool.client

    monkeypatch.setattr("redis.ConnectionPool.from_url", _fake_from_url)
    monkeypatch.setattr("redis.Redis", _fake_redis)
    cache_factory(backend="redis")

    from market_scraper.utils import cache

    cache.set("https://exemplo.com/redis", "<html>redis</html>", ttl_seconds=30)
    assert cache.get("https://exemplo.com/redis") == "<html>redis</html>"
    assert SCRAPER_CACHE_SIZE._value.get() == 1.0
    assert SCRAPER_CACHE_HIT_RATE._value.get() == 1.0

def test_redis_backend_records_errors(monkeypatch: pytest.MonkeyPatch, cache_factory: Callable[..., None]) -> None:
    """ Falhas do adapter Redis devem incrementar métrica dedicada sem propagar exceção """
    class _FailingRedis:
        """ Cliente Redis que falha ao executar ``pipeline`` """

        def pipeline(self) -> "_FailingPipeline":
            return _FailingPipeline()

        def smembers(self, *_: object, **__: object) -> set[str]:
            """Retorna conjunto vazio para compatibilidade com ``clear``"""
            return set()

        def delete(self, *_: object, **__: object) -> int:
            """Retorna zero ao tentar remover chaves inexistentes"""
            return 0

        def srem(self, *_: object, **__: object) -> int:
            """Retorna zero ao tentar remover membros inexistentes"""
            return 0

        def scard(self, *_: object, **__: object) -> int:
            """Retorna zero para cardinalidade do índice auxiliar"""
            return 0
        
    class _FailingPipeline:
        """ Pipeline que lança ``RuntimeError`` ao executar comandos """

        def set(self, *_: object, **__: object) -> "_FailingPipeline":
            return self

        def sadd(self, *_: object, **__: object) -> "_FailingPipeline":
            return self

        def execute(self) -> None:
            raise redis.exceptions.RedisError("falha")

    failing_client = _FailingRedis()

    def _fake_from_url(*_: object, **__: object) -> SimpleNamespace:
        return SimpleNamespace(client=failing_client)

    def _fake_redis(*args: object, **kwargs: object) -> _FailingRedis:
        connection_pool = kwargs.get("connection_pool") or args[0]
        return connection_pool.client

    monkeypatch.setattr("redis.ConnectionPool.from_url", _fake_from_url)
    monkeypatch.setattr("redis.Redis", _fake_redis)
    cache_factory(backend="redis")

    from market_scraper.utils import cache

    cache.set("https://exemplo.com/erro", "<html>falha</html>", ttl_seconds=30)
    assert (
        SCRAPER_CACHE_REDIS_ERRORS_TOTAL.labels(operation="set")._value.get()
        == 1.0
    )
    