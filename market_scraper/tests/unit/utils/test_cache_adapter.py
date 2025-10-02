
from __future__ import annotations

from dataclasses import dataclass, field
from types import MethodType
from typing import Any, Dict, List, Optional

import pytest

from market_scraper.utils.cache_adapter import CacheAdapter, NOT_MODIFIED


@dataclass
class DummyAsyncCacheManager:
    """ Gerenciador assíncrono falso para verificar chamadas do adaptador """
    store: Dict[tuple[str, str], Dict[str, Any]] = field(default_factory=dict)
    touches: List[tuple[str, str, Optional[int]]] = field(default_factory=list)

    async def get(self, *, marketplace: str, url: str) -> Optional[Dict[str, Any]]:
        return self.store.get((marketplace, url))
    
    async def set(
        self,
        *,
        marketplace: str,
        url: str,
        value: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> None:
        self.store[(marketplace, url)] = value

    async def touch(
        self,
        *,
        marketplace: str,
        url: str,
        ttl: Optional[int] = None,
    ) -> None:
        self.touches.append((marketplace, url, ttl))

@pytest.mark.asyncio()
async def test_set_and_get_with_version() -> None:
    """ Garante que ``set`` e ``get`` funcionam com namespace e versão aplicados """
    manager = DummyAsyncCacheManager()
    adapter = CacheAdapter(
        cache_manager=manager,
        legacy_cache_manager=manager,
        data_namespace="produto",
        version="v1",
    )

    url = "https://example.com/item"
    value = {"data": {"name": "Notebook"}}

    await adapter.set(marketplace="mercadolivre", url=url, value=value)
    result = await adapter.get(marketplace="mercadolivre", url=url)

    assert result == value

@pytest.mark.asyncio()
async def test_get_uses_fallback_when_version_missing() -> None:
    """ Valida que o adaptador consulta o cache legado quando necessário """
    manager = DummyAsyncCacheManager()
    adapter = CacheAdapter(
        cache_manager=manager,
        legacy_cache_manager=manager,
        data_namespace="produto",
        version="v2",
    )

    url = "https://example.com/legacy"
    legacy_key = ("mercado", url)
    manager.store[legacy_key] = {"legacy": True}

    result = await adapter.get(marketplace="mercado", url=url)

    assert result == {"legacy": True}

@pytest.mark.asyncio()
async def test_touch_propagates_to_legacy() -> None:
    """ Confirma que ``touch`` renova o TTL no namespace atual e no legado """
    manager = DummyAsyncCacheManager()
    adapter = CacheAdapter(
        cache_manager=manager,
        legacy_cache_manager=manager,
        data_namespace="produto",
        version="v1",
    )

    await adapter.touch(marketplace="mercado", url="https://example.com/touch", ttl=120)

    assert ("produto|mercado|v=v1", "https://example.com/touch", 120) in manager.touches
    assert ("mercado", "https://example.com/touch", 120) in manager.touches

@pytest.mark.asyncio()
async def test_get_headers_falls_back_to_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Verifica que cabeçalhos são recuperados quando o namespace novo está vazio """
    stored: Dict[str, Dict[str, Optional[str]]] = {}

    async def fake_get(self: CacheAdapter, key: str) -> Dict[str, Optional[str]]:
        return stored.get(key, {"etag": None, "last_modified": None})

    adapter = CacheAdapter(
        cache_manager=DummyAsyncCacheManager(),
        legacy_cache_manager=DummyAsyncCacheManager(),
        data_namespace="produto",
        headers_namespace="http",
        version="v5",
    )

    monkeypatch.setattr(adapter, "_get_headers_for_key", MethodType(fake_get, adapter))

    url = "https://example.com/header"
    stored[url] = {"etag": "legacy", "last_modified": "ontem"}

    headers = await adapter.get_headers(url)

    assert headers == {"etag": "legacy", "last_modified": "ontem"}

@pytest.mark.asyncio()
async def test_store_headers_uses_versioned_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante que os cabeçalhos sejam persistidos utilizando o namespace atual """
    stored: Dict[str, Dict[str, Optional[str]]] = {}

    async def fake_store(
        self: CacheAdapter,
        key: str,
        *,
        etag: Optional[str],
        last_modified: Optional[str],
        ttl_seconds: int | None,
    ) -> None:
        stored[key] = {"etag": etag, "last_modified": last_modified}

    adapter = CacheAdapter(
        cache_manager=DummyAsyncCacheManager(),
        legacy_cache_manager=DummyAsyncCacheManager(),
        headers_namespace="http",
        version="beta",
    )

    monkeypatch.setattr(adapter, "_store_headers_for_key", MethodType(fake_store, adapter))

    url = "https://example.com/new"
    await adapter.store_headers(url, etag="novo", last_modified="agora")

    assert stored["http|https://example.com/new|v=beta"] == {"etag": "novo", "last_modified": "agora"}

@pytest.mark.asyncio()
async def test_check_or_update_signature_respects_legacy_not_modified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ Confere que o adaptador retorna ``NOT_MODIFIED`` quando o legado indica ausência de mudanças. """
    results: Dict[str, List[Any]] = {}
    calls: List[tuple[str, str, bool]] = []
    
    adapter = CacheAdapter(
        cache_manager=DummyAsyncCacheManager(),
        legacy_cache_manager=DummyAsyncCacheManager(),
        signature_namespace="sig",
        version="v4",
    )

    legacy_key = adapter._url_key(
        "https://example.com/sig",
        config=adapter.signature_config,
        include_namespace=False,
        include_version=False,
    )
    versioned_key = adapter._url_key(
        "https://example.com/sig",
        config=adapter.signature_config,
    )

    results[legacy_key] = [NOT_MODIFIED]
    results[versioned_key] = ["updated"]

    async def fake_check(
        self: CacheAdapter,
        url: str,
        html: str,
        *,
        update_if_not_modified: bool,
    ) -> Any:
        calls.append((url, html, update_if_not_modified))
        queue = results.get(url)
        if queue:
            return queue.pop(0)
        return "signature::" + url
    
    monkeypatch.setattr(adapter, "_check_signature_for_key", MethodType(fake_check, adapter))

    result = await adapter.check_or_update_signature("https://example.com/sig", "<html></html>")

    assert result is NOT_MODIFIED
    assert calls[0] == (legacy_key, "<html></html>", True)
    assert calls[1] == (versioned_key, "<html></html>", False)

@pytest.mark.asyncio()
async def test_check_or_update_signature_returns_new_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """ Garante que uma nova asssinatura seja retornada quando o legado mudou """
    results: Dict[str, List[Any]] = {}
    calls: List[tuple[str, str, bool]] = []

    adapter = CacheAdapter(
        cache_manager=DummyAsyncCacheManager(),
        legacy_cache_manager=DummyAsyncCacheManager(),
        signature_namespace="sig",
        version="v7",
    )

    legacy_key = adapter._url_key(
        "https://example.com/sig-change",
        config=adapter.signature_config,
        include_namespace=False,
        include_version=False,
    )
    versioned_key = adapter._url_key(
        "https://example.com/sig-change",
        config=adapter.signature_config,
    )

    results[legacy_key] = ["antigo"]
    results[versioned_key] = ["novo"]

    async def fake_check(
        self: CacheAdapter,
        url: str,
        html: str,
        *,
        update_if_not_modified: bool,
    ) -> Any:
        calls.append((url, html, update_if_not_modified))
        queue = results.get(url)
        if queue:
            return queue.pop(0)
        return "signature::" + url
    
    monkeypatch.setattr(adapter, "_check_signature_for_key", MethodType(fake_check, adapter))

    result = await adapter.check_or_update_signature(
        "https://example.com/sig-change", "<body>novo</body>"
    )

    assert result == "novo"
    assert calls[0] == (legacy_key, "<body>novo</body>", True)
    assert calls[1] == (versioned_key, "<body>novo</body>", True)

    