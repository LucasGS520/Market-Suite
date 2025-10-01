""" Testes unitários para o ``CacheAdapter`` """

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from market_scraper.utils.cache_adapter import CacheAdapter, NOT_MODIFIED


@dataclass
class DummyCacheManager:
    """ Falso gerenciador para inspecionar chamadas do adaptador """
    store: Dict[tuple[str, str], Dict[str, Any]] = field(default_factory=dict)
    touches: List[tuple[str, str, Optional[int]]] = field(default_factory=list)

    def get(self, *, marketplace: str, url: str) -> Optional[Dict[str, Any]]:
        return self.store.get((marketplace, url))
    
    def set(
        self,
        *,
        marketplace: str,
        url: str,
        value: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> None:
        self.store[(marketplace, url)] = value

    def touch(
        self,
        *,
        marketplace: str,
        url: str,
        ttl: Optional[int] = None,
    ) -> None:
        self.touches.append((marketplace, url, ttl))

class SignatureDouble:
    """ Simula a assinatura de conteúdo permitindo filas de respostas """
    def __init__(self, url: str) -> None:
        self.url = url
        self.queued_results: List[Any] = []
        self.checked_payloads: List[str] = []
        self.checked_payloads: List[str] = []

    def queue(self, *results: Any) -> None:
        """ Configura respostas subsequentes para ``check_or_update`` """
        self.queued_results.extend(results)

    def check_or_update(self, html: str) -> Any:
        self.checked_payloads.append(html)
        if self.queued_results:
            return self.queued_results.pop(0)
        return f"signature::{self.url}"
    
    def update(self, html: str) -> str:
        self.updated_payloads.append(html)
        return f"updated::{self.url}"
    
class SignatureFactory:
    """ Fábrica de ``SignatureDouble`` com configurações por URL """
    def __init__(self) -> None:
        self.instances: Dict[str, SignatureDouble] = {}
        self.preconfigured: Dict[str, List[Any]] = {}

    def configure(self, url: str, *results: Any) -> None:
        """ Define resultados que deverão ser retornados para a URL informada """
        self.preconfigured[url] = list(results)

    def __call__(self, url: str) -> SignatureDouble:
        if url not in self.instances:
            instance = SignatureDouble(url)
            if url in self.preconfigured:
                instance.queue(*self.preconfigured[url])
            self.instances[url] = instance
        return self.instances[url]
    
def test_set_and_get_with_version() -> None:
    """ Garante que ``set`` e ``get`` funcionem ao aplicar namespace e versão """
    manager = DummyCacheManager()
    adapter = CacheAdapter(
        cache_manager=manager,
        legacy_cache_manager=manager,
        data_namespace="produto",
        version="v1",
    )
    url = "https://example.com/item"
    value = {"data": {"name": "Notebook"}}

    adapter.set(marketplace="mercadolivre", url=url, value=value)
    result = adapter.get(marketplace="mercadolivre", url=url)

    assert result == value

def test_get_uses_fallback_when_version_missing() -> None:
    """ Valida que o adaptador consulta o cache legado quando o novo não contém dados """
    manager = DummyCacheManager()
    adapter = CacheAdapter(
        cache_manager=manager,
        legacy_cache_manager=manager,
        data_namespace="produto",
        version="v2",
    )
    url = "https://example.com/legacy"
    legacy_key = ("mercado", url)
    manager.store[legacy_key] = {"legacy": True}

    result = adapter.get(marketplace="mercado", url=url)

    assert result == {"legacy": True}

def test_touch_propagates_to_legacy() -> None:
    """ Confirma que ``touch`` renova o TTL do registro atual e legado """
    manager = DummyCacheManager()
    adapter = CacheAdapter(
        cache_manager=manager,
        legacy_cache_manager=manager,
        data_namespace="produto",
        version="v1",
    )

    adapter.touch(marketplace="mercado", url="https://example.com/touch", ttl=120)

    assert ("produto|mercado|v=v1", "https://example.com/touch", 120) in manager.touches
    assert ("mercado", "https://example.com/touch", 120) in manager.touches

def test_get_headers_falls_back_to_legacy() -> None:
    """ Verifica que cabeçalhos legados são recuperados quando o namespace novo está vazio """
    stored: Dict[str, Dict[str, Optional[str]]] = {}

    def fake_get(url: str) -> Dict[str, Optional[str]]:
        return stored.get(url, {"etag": None, "last_modified": None})
    
    def fake_store(url: str, **kwargs: Any) -> None:
        stored[url] = {"etag": kwargs.get("etag"), "last_modified": kwargs.get("last_modified")}

    adapter = CacheAdapter(
        cache_manager=DummyCacheManager(),
        legacy_cache_manager=DummyCacheManager(),
        data_namespace="produto",
        headers_namespace="http",
        version="v5",
        headers_getter=fake_get,
        headers_store=fake_store,
    )

    url = "https://example.com/header"
    stored[url] = {"etag": "legacy", "last_modified": "ontem"}

    headers = adapter.get_headers(url)

    assert headers == {"etag": "legacy", "last_modified": "ontem"}

def test_store_headers_uses_versioned_key() -> None:
    """ Garante que os cabeçalhos sejam persistidos utilizando o namespace atual """
    stored: Dict[str, Dict[str, Optional[str]]] = {}

    def fake_get(url: str) -> Dict[str, Optional[str]]:
        return stored.get(url, {"etag": None, "last_modified": None})
    
    def fake_store(url: str, **kwargs: Any) -> None:
        stored[url] = {"etag": kwargs.get("etag"), "last_modified": kwargs.get("last_modified")}

    adapter = CacheAdapter(
        cache_manager=DummyCacheManager(),
        legacy_cache_manager=DummyCacheManager(),
        headers_namespace="http",
        version="beta",
        headers_getter=fake_get,
        headers_store=fake_store,
    )

    url = "https://example.com/new"
    adapter.store_headers(url, etag="novo", last_modified="agora")

    assert stored["http|https://example.com/new|v=beta"] == {"etag": "novo", "last_modified": "agora"}

def test_check_or_update_signature_respects_legacy_not_modified() -> None:
    """Confirma que o adaptador retorna ``NOT_MODIFIED`` quando o legado aponta ausência de mudanças."""
    factory = SignatureFactory()
    adapter = CacheAdapter(
        cache_manager=DummyCacheManager(),
        legacy_cache_manager=DummyCacheManager(),
        signature_namespace="sig",
        version="v4",
        signature_factory=factory,
    )

    url = "https://example.com/sig"
    factory.configure(url, NOT_MODIFIED)

    result = adapter.check_or_update_signature(url, "<html></html>")

    assert result is NOT_MODIFIED
    versioned_key = "sig|https://example.com/sig|v=v4"
    assert factory.instances[versioned_key].updated_payloads == ["<html></html>"]


def test_check_or_update_signature_returns_new_value() -> None:
    """Valida que o novo namespace calcula assinatura quando o legado muda."""
    factory = SignatureFactory()
    adapter = CacheAdapter(
        cache_manager=DummyCacheManager(),
        legacy_cache_manager=DummyCacheManager(),
        signature_namespace="sig",
        version="v7",
        signature_factory=factory,
    )

    url = "https://example.com/sig-change"
    factory.configure(url, "antigo")
    versioned_key = "sig|https://example.com/sig-change|v=v7"
    factory.configure(versioned_key, "novo")

    result = adapter.check_or_update_signature(url, "<body>novo</body>")

    assert result == "novo"
    assert factory.instances[url].checked_payloads == ["<body>novo</body>"]
    assert factory.instances[versioned_key].checked_payloads == ["<body>novo</body>"]
    