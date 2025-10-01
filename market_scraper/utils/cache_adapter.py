""" Adaptador de cache para consolidar acesso 

Este módulo fornece a classe :class:`CacheAdapter`, responsável por
encapsular o ``IntelligentCacheManager`` e os utilitários de cache HTTP.
Com ela, demais componentes do scraper interagem com uma interface
única para leitura e escrita de dados, cabeçalhos condicionais e
assinaturas de conteúdo. O adaptador permite configurar prefixos e
versionamento para facilitar migrações de chaves sem quebrar
compatibilidade com registros legados.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
import os

from market_scraper.utils.intelligent_cache import IntelligentCacheManager
from market_scraper.utils.http_cache import (
    get_cache_headers as _get_cache_headers,
    store_cache_headers as _store_cache_headers,
    ContentSignature,
    NOT_MODIFIED,
)


@dataclass
class _NamespaceConfig:
    """ Define parâmetros opcionais de versionamento para cada recurso """
    namespace: Optional[str]
    version: Optional[str]

    def apply(self, value: str, *, include_namespace: bool = True, include_version: bool = True) -> str:
        """ Monta uma representação contendo namespace e versão quando configurados """
        parts: list[str] = []
        if include_namespace and self.namespace:
            parts.append(self.namespace)
        parts.append(value)
        if include_version and self.version:
            parts.append(f"v={self.version}")
        return "|".join(parts)
    
class CacheAdapter:
    """ Centraliza operações de cache com suporte a versionamento """
    def __init__(
        self,
        *,
        cache_manager: IntelligentCacheManager | None = None,
        legacy_cache_manager: IntelligentCacheManager | None = None,
        data_namespace: str | None = None,
        headers_namespace: str | None = None,
        signature_namespace: str | None = None,
        version: str | None = None,
        fallback_to_legacy: bool = True,
        headers_getter: Callable[[str], Dict[str, Optional[str]]] = _get_cache_headers,
        headers_store: Callable[..., None] = _store_cache_headers,
        signature_factory: Callable[[str], ContentSignature] | None = None,
        write_legacy_on_set: bool = False,
        write_legacy_headers: bool = False,
    ) -> None:
        """ Configura o adaptador permitindo ajustar namespace, versão e fallback """
        self.cache_manager = cache_manager or IntelligentCacheManager()
        self.legacy_manager = legacy_cache_manager or self.cache_manager
        self.data_config = _NamespaceConfig(namespace=data_namespace, version=version)
        self.headers_config = _NamespaceConfig(namespace=headers_namespace, version=version)
        self.signature_config = _NamespaceConfig(namespace=signature_namespace, version=version)
        fallback_requested = any(
            value is not None
            for value in (version, data_namespace, headers_namespace, signature_namespace)
        ) or (legacy_cache_manager is not None and legacy_cache_manager is not self.cache_manager)
        self._fallback_enabled = fallback_to_legacy and fallback_requested
        self._headers_getter = headers_getter
        self._headers_store = headers_store
        self._signature_factory = signature_factory or (lambda url: ContentSignature(url))
        self._write_legacy_on_set = write_legacy_on_set
        self._write_legacy_headers = write_legacy_headers

    def _marketplace_key(self, marketplace: Optional[str], *, include_version: bool = True, include_namespace: bool = True) -> str:
        """ Normaliza o marketplace aplicando namespace e versão quando necessário """
        normalized = marketplace or "unknown"
        return self.data_config.apply(
            normalized,
            include_namespace=include_namespace,
            include_version=include_version,
        )
    
    def _url_key(
        self,
        url: str,
        *,
        config: _NamespaceConfig,
        include_version: bool = True,
        include_namespace: bool = True,
    ) -> str:
        """ Aplica namespace e versão à URL informada conforme configuração """
        return config.apply(
            url,
            include_namespace=include_namespace,
            include_version=include_version,
        )
    
    def get(self, *, marketplace: str | None, url: str) -> Optional[Dict[str, Any]]:
        """ Busca um item no cache, recorrendo ao namespace legado se necessário """
        value = self.cache_manager.get(
            marketplace=self._marketplace_key(marketplace),
            url=url,
        )
        if value is not None or not self._fallback_enabled:
            return value
        return self.legacy_manager.get(
            marketplace=self._marketplace_key(marketplace, include_version=False, include_namespace=False),
            url=url,
        )
    
    def set(
        self,
        *,
        marketplace: str | None,
        url: str,
        value: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> None:
        """ Armazena o valor no cache principal e opcionalmente replica no legado """
        self.cache_manager.set(
            marketplace=self._marketplace_key(marketplace),
            url=url,
            value=value,
            ttl=ttl,
        )
        if self._fallback_enabled and self._write_legacy_on_set:
            self.legacy_manager.set(
                marketplace=self._marketplace_key(marketplace, include_version=False, include_namespace=False),
                url=url,
                value=value,
                ttl=ttl,
            )

    def touch(
        self,
        *,
        marketplace: str | None,
        url: str,
        ttl: Optional[int] = None,
    ) -> None:
        """ Renova o TTL do registro ativo e do legado quando aplicável """
        self.cache_manager.touch(
            marketplace=self._marketplace_key(marketplace),
            url=url,
            ttl=ttl,
        )
        if self._fallback_enabled:
            self.legacy_manager.touch(
                marketplace=self._marketplace_key(marketplace, include_version=False, include_namespace=False),
                url=url,
                ttl=ttl,
            )

    def get_headers(
        self,
        url: str,
    ) -> Dict[str, Optional[str]]:
        """ Obtém cabeçalhos condicionais, respeitando fallback para o namespace antigo """
        versioned_url = self._url_key(url, config=self.headers_config)
        headers = self._headers_getter(versioned_url)
        if self._fallback_enabled and not any(headers.values()):
            legacy_url = self._url_key(
                url,
                config=self.headers_config,
                include_version=False,
                include_namespace=False,
            )
            return self._headers_getter(legacy_url)
        return headers
    
    def store_headers(
        self,
        url: str,
        *,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        ttl_seconds: int | None = None,
    ) -> None:
        """ Persiste cabeçalhos HTTP usando namespace atual e opcionalmente o legado """
        versioned_url = self._url_key(url, config=self.headers_config)
        self._headers_store(
            versioned_url,
            etag=etag,
            last_modified=last_modified,
            ttl_seconds=ttl_seconds,
        )
        if self._fallback_enabled and self._write_legacy_headers:
            legacy_url = self._url_key(
                url,
                config=self.headers_config,
                include_version=False,
                include_namespace=False,
            )
            self._headers_store(
                legacy_url,
                etag=etag,
                last_modified=last_modified,
                ttl_seconds=ttl_seconds,
            )

    def check_or_update_signature(
        self, 
        url: str, 
        html: str
    ) -> Any:
        """ verifica a assinatura do conteúdo, sincronizando dados entre versões """
        if self._fallback_enabled:
            legacy_signature = self._signature_factory(
                self._url_key(
                    url,
                    config=self.signature_config,
                    include_version=False,
                    include_namespace=False,
                )
            )
            legacy_result = legacy_signature.check_or_update(html)
            if legacy_result is NOT_MODIFIED:
                versioned = self._signature_factory(
                    self._url_key(url, config=self.signature_config)
                )
                versioned.update(html)
                return NOT_MODIFIED
        versioned_signature = self._signature_factory(
            self._url_key(url, config=self.signature_config)
        )
        return versioned_signature.check_or_update(html)
    
def _load_namespace(env_name: str) -> Optional[str]:
    """ Carrega valores de namespace das variáveis de ambiente, ignorando vazio """
    value = os.getenv(env_name, "").strip()
    return value or None

default_version = _load_namespace("SCRAPER_CACHE_VERSION")
default_namespace = _load_namespace("SCRAPER_CACHE_NAMESPACE")

cache_adapter = CacheAdapter(
    data_namespace=default_namespace,
    headers_namespace=default_namespace,
    signature_namespace=default_namespace,
    version=default_version,
)

__all__ = ["CacheAdapter", "cache_adapter", "NOT_MODIFIED"]
