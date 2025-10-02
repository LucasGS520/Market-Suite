""" Adaptador de cache assíncrono com fallback local e proteção contra stampede

Este módulo concentra todas as operações de cache utilizadas pelo 
``market_scraper`` em uma única classe de alto nível. A implementação foi
refatorada para utilizar ``redis.asyncio`` com chamadas ``await`` e inclui
recursos adicionais como jitter de expiração, bloqueios distribuídos e fallback
local baseado em ``cachetools``.

Principais responsabilidades:

* Persistir e recuperar dados estruturados do cache distribuído
* Armazenar cabeçalhos condicionais (``ETag`` e ``Last-Modified``)
* Gerenciar assinaturas de conteúdo para detectar páginas não modificadas
* Oferecer contingência local quando o Redis estiver indisponível
* Evitar efeito "cache stampede" por meio de expiração antecipada e locks
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import secrets
import time
from dataclasses import dataclass
import inspect
from typing import Any, Callable, Dict, Optional

from cachetools import TTLCache
import redis.asyncio as redis
import structlog

from market_scraper.core.config_scraper import settings
from shared.metrics.metrics_scraper import (
    SCRAPER_CACHE_LATENCY_SECONDS,
    SCRAPER_CACHE_LOCAL_SIZE,
    SCRAPER_CACHE_LOCK_TOTAL,
    SCRAPER_CACHE_LOOKUPS_TOTAL,
)
from shared.utils.logging_utils import sanitize_log_data


#Sentinela utilizada para indicar ausência de alterações no conteúdo HTML
NOT_MODIFIED = object()

#Configurações padrão herdadas do cache antigo para preservar compatibilidade
DEFAULT_CACHE_PREFIX = "scraper:product:"
DEFAULT_CACHE_TTL = int(settings.CACHE_BASE_TTL)
DEFAULT_ETAG_PREFIX = "http_cache:etag:"
DEFAULT_LAST_MODIFIED_PREFIX = "http_cache:last_modified:"
DEFAULT_SIGNATURE_PREFIX = "http_cache:signature:"

logger = structlog.get_logger(__name__)


@dataclass
class _NamespaceConfig:
    """ Representa ajustes de namespace e versão aplicados às chaves """
    namespace: Optional[str]
    version: Optional[str]

    def apply(
        self,
        value: str,
        *,
        include_namespace: bool = True,
        include_version: bool = True,
    ) -> str:
        """ Concatena namespace e versão quando configurados """
        parts: list[str] = []
        if include_namespace and self.namespace:
            parts.append(self.namespace)
        parts.append(value)
        if include_version and self.version:
            parts.append(f"v={self.version}")
        return "|".join(parts)
    
@dataclass
class _LocalCacheEntry:
    """ Estrutura com metadados utilizados pelo cache local de contingência """
    value: Dict[str, Any]
    expires_at: float
    ttl: int

    @property
    def remaining(self) -> float:
        """ Retorna o tempo restante em segundos antes de expiração """
        return max(0.0, self.expires_at - time.monotonic())
    
class AsyncCacheBackend:
    """ Executa operações assíncronas no Redis com fallback local seguro """
    def __init__(
        self,
        *,
        prefix: str = DEFAULT_CACHE_PREFIX,
        default_ttl: int = DEFAULT_CACHE_TTL,
        redis_url: str | None = None,
        redis_factory: Callable[[], redis.Redis | None] | None = None,
        local_maxsize: int = 1024,
        jitter_range: tuple[float, float] = (1.0, 30.0),
        lock_timeout: int = 5,
    ) -> None:
        """ Configura a instância com parâmetros padrão e dependências """
        self.prefix = prefix
        self.default_ttl = int(default_ttl)
        self.redis_url = redis_url or settings.redis_url
        self._redis_factory = redis_factory
        self._redis: redis.Redis | None = None
        self._redis_lock = asyncio.Lock()
        self._local_cache: TTLCache[str, _LocalCacheEntry] = TTLCache(
            maxsize=local_maxsize,
            ttl=default_ttl,
        )
        self._local_lock = asyncio.Lock()
        self.jitter_range = jitter_range
        self.lock_timeout = lock_timeout

    async def _get_redis(self) -> redis.Redis | None:
        """ Obtém ou inicializa o cliente Redis assíncrono com validação básica """
        if self._redis is not None:
            return self._redis
        
        async with self._redis_lock:
            if self._redis is not None:
                return self._redis
            try:
                if self._redis_factory is not None:
                    candidate = self._redis_factory()
                    if inspect.isawaitable(candidate):
                        candidate = await candidate
                else:
                    candidate = redis.Redis.from_url(
                        self.redis_url,
                        encoding="utf-8",
                        decode_responses=False,
                    )
                if candidate is None:
                    raise ValueError("redis_factory returned None")
                required_methods = (
                    "setex", 
                    "set",
                    "get", 
                    "ttl", 
                    "delete",
                    "expire",
                    "eval",
                )
                missing = [name for name in required_methods if not hasattr(candidate, name)]
                if missing:
                    raise AttributeError(
                        "client Redis incompatible: missing methods " + ", ".join(sorted(missing))
                    )
                self._redis = candidate
            except Exception as err:
                logger.warning(
                    "initialize_redis_async_failed",
                    error=sanitize_log_data(str(err)),
                    error_type=err.__class__.__name__,
                )
                self._redis = None
        return self._redis
    
    def _hash_content(self, marketplace: str, url: str) -> str:
        """ Calcula hash único combinando marketplace e URL """
        raw = f"{marketplace}:{url}"
        return hashlib.sha256(raw.encode()).hexdigest()
    
    def _build_key(self, marketplace: str, url: str) -> str:
        """ Monta a chave final utilizada no Redis """
        return f"{self.prefix}{self._hash_content(marketplace, url)}"
    
    def _apply_jitter(self, ttl: int) -> int:
        """ Aplica jitter aleatório para antecipar expiração e evitar stampede """
        lower, upper = self.jitter_range
        if upper <= 0:
            return max(1, ttl)
        jitter = random.uniform(lower, min(upper, ttl))
        return max(1, int(ttl - jitter))
    
    def _should_consider_stale(self, ttl_remaining: float) -> bool:
        """ Determina se o item deve ser tratado como expirado antecipadamente """
        if ttl_remaining <= 0:
            return True
        lower, upper = self.jitter_range
        if upper <= 0:
            return False
        threshold = random.uniform(lower, upper)
        return ttl_remaining <= threshold
    
    async def _load_local(self, key: str) -> Optional[Dict[str, Any]]:
        """ Recupera o valor do cache local aplicando políticas de expiração """
        async with self._local_lock:
            entry = self._local_cache.get(key)
            if entry is None:
                return None
            if entry.remaining <= 0:
                self._local_cache.pop(key, None)
                SCRAPER_CACHE_LOCAL_SIZE.set(len(self._local_cache))
                SCRAPER_CACHE_LOOKUPS_TOTAL.labels(
                    backend="local",
                    outcome="expired",
                ).inc()
                return None
            if self._should_consider_stale(entry.remaining):
                self._local_cache.pop(key, None)
                SCRAPER_CACHE_LOCAL_SIZE.set(len(self._local_cache))
                SCRAPER_CACHE_LOOKUPS_TOTAL.labels(
                    backend="local",
                    outcome="stale",
                ).inc()
                return None
            SCRAPER_CACHE_LOOKUPS_TOTAL.labels(
                backend="local",
                outcome="hit",
            ).inc()
            return entry.value
        
    async def _store_local(self, key: str, value: Dict[str, Any], ttl: int) -> None:
        """ Persiste o valor no cache local respeitando o TTL informado """
        now = time.monotonic()
        entry = _LocalCacheEntry(
            value=value,
            expires_at=now + ttl,
            ttl=ttl,
        )
        async with self._local_lock:
            self._local_cache[key] = entry
            SCRAPER_CACHE_LOCAL_SIZE.set(len(self._local_cache))

    async def _touch_local(self, key: str, ttl: int) -> None:
        """ Atualiza o TTL do item em cache local quando presente """
        async with self._local_lock:
            entry = self._local_cache.get(key)
            if entry is None:
                return
            entry.ttl = ttl
            entry.expires_at = time.monotonic() + ttl
            self._local_cache[key] = entry
            SCRAPER_CACHE_LOCAL_SIZE.set(len(self._local_cache))

    async def get(
        self,
        *,
        marketplace: str | None,
        url: str,
    ) -> Optional[Dict[str, Any]]:
        """ Recupera dados do cache aplicando fallback local quando necessário """
        marketplace = marketplace or "unknown"
        key = self._build_key(marketplace, url)
        start = time.perf_counter()
        client = await self._get_redis()

        if client is None:
            SCRAPER_CACHE_LOOKUPS_TOTAL.labels(
                backend="redis",
                outcome="unavailable",
            ).inc()
        else:
            try:
                raw_value = await client.get(key)
                if raw_value is not None:
                    ttl_remaining = await client.ttl(key)
                    considered_stale = (
                        ttl_remaining > 0 and self._should_consider_stale(ttl_remaining)
                    )
                    if considered_stale:
                        SCRAPER_CACHE_LOOKUPS_TOTAL.labels(
                            backend="redis",
                            outcome="stale",
                        ).inc()
                        await client.delete(key)
                    else:
                        SCRAPER_CACHE_LOOKUPS_TOTAL.labels(
                            backend="redis",
                            outcome="hit",
                        ).inc()
                        SCRAPER_CACHE_LATENCY_SECONDS.labels(operation="get").observe(
                            time.perf_counter() - start
                        )
                        try:
                            return json.loads(raw_value)
                        except json.JSONDecodeError as err:
                            logger.warning(
                                "decode_cache_failed",
                                key=key,
                                error=sanitize_log_data(str(err)),
                            )
                else:
                    SCRAPER_CACHE_LOOKUPS_TOTAL.labels(
                        backend="redis",
                        outcome="miss",
                    ).inc()
            except Exception as err:
                SCRAPER_CACHE_LOOKUPS_TOTAL.labels(
                    backend="redis",
                    outcome="error",
                ).inc()
                logger.warning(
                    "falha_cache_redis_get",
                    key=key,
                    outcome=sanitize_log_data(str(err)),
                )

        value = await self._load_local(key)
        SCRAPER_CACHE_LATENCY_SECONDS.labels(operation="get").observe(
            time.perf_counter() - start
        )
        if value is None:
            SCRAPER_CACHE_LOOKUPS_TOTAL.labels(
                backend="local",
                outcome="miss",
            ).inc()
        return value
    
    async def set(
        self,
        *,
        marketplace: str | None,
        url: str,
        value: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> None:
        """ Armazena o valor no Redis e replica no cache local """
        marketplace = marketplace or "unknown"
        ttl = int(ttl) if ttl is not None else self.default_ttl
        key = self._build_key(marketplace, url)
        start = time.perf_counter()
        client = await self._get_redis()

        payload = json.dumps(value)
        effective_ttl = self._apply_jitter(ttl)
        if client is not None:
            try:
                await client.setex(key, effective_ttl, payload)
            except Exception as err:
                SCRAPER_CACHE_LOOKUPS_TOTAL.labels(
                    backend="redis",
                    outcome="error",
                ).inc()
                logger.warning(
                    "cache_redis_set_failed",
                    key=key,
                    error=sanitize_log_data(str(err)),
                )

        await self._store_local(key, value, ttl)
        SCRAPER_CACHE_LATENCY_SECONDS.labels(operation="set").observe(
            time.perf_counter() - start
        )

    async def _acquire_lock(
        self,
        client: redis.Redis,
        key: str,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """ Tenta adquirir um lock e retorna ``(acquired, lock_key, token)`` """
        token = secrets.token_hex(16)
        lock_key = f"{key}:lock"
        try:
            acquired = await client.set(lock_key, token, nx=True, ex=self.lock_timeout)
            if acquired:
                SCRAPER_CACHE_LOCK_TOTAL.labels(outcome="acquired").inc()
                return True, lock_key, token
            SCRAPER_CACHE_LOCK_TOTAL.labels(outcome="miss").inc()
            return False, None, None
        except Exception as err:
            SCRAPER_CACHE_LOCK_TOTAL.labels(outcome="error").inc()
            logger.warning(
                "falha_cache_lock",
                key=key,
                error=sanitize_log_data(str(err)),
            )
            return False, None, None
        
    async def _release_lock(
        self,
        client: redis.Redis,
        lock_key: str,
        token: str,
    ) -> None:
        """ Libera o lock apenas quando o token coincide """
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        else
            return 0
        end
        """
        try:
            await client.eval(script, 1, lock_key, token)
        except Exception as err:
            logger.warning(
                "falha_cache_unlock",
                key=lock_key,
                error=sanitize_log_data(str(err)),
            )

    async def touch(
        self,
        *,
        marketplace: str | None,
        url: str,
        ttl: Optional[int] = None,
    ) -> None:
        """ Atualiza o TTL do item no Redis utilizando lock para evitar stampede """
        marketplace = marketplace or "unknown"
        ttl = int(ttl) if ttl is not None else self.default_ttl
        key = self._build_key(marketplace, url)
        start = time.perf_counter()
        client = await self._get_redis()

        if client is not None:
            acquired, lock_key, token = await self._acquire_lock(client, key)
            if acquired and token is not None and lock_key is not None:
                try:
                    await client.expire(key, self._apply_jitter(ttl))
                except Exception as err:
                    logger.warning(
                        "cache_touch_failed",
                        key=key,
                        error=sanitize_log_data(str(err)),
                    )
                finally:
                    await self._release_lock(client, lock_key, token)
        await self._touch_local(key, ttl)
        SCRAPER_CACHE_LATENCY_SECONDS.labels(operation="touch").observe(
            time.perf_counter() - start
        )

def _hash_url(url: str) -> str:
    """ Gera hash SHA256 para o texto informado """
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


class CacheAdapter:
    """ Centraliza operações de cache com suporte a versionamento """
    def __init__(
        self,
        *,
        cache_manager: AsyncCacheBackend | None = None,
        legacy_cache_manager: AsyncCacheBackend | None = None,
        data_namespace: str | None = None,
        headers_namespace: str | None = None,
        signature_namespace: str | None = None,
        version: str | None = None,
        fallback_to_legacy: bool = True,
        redis_url: str | None = None,
        redis_factory: Callable[[], redis.Redis | None] | None = None,
    ) -> None:
        """ COnfigura o adaptador de cache definindo namespaces e dependências """
        manager = cache_manager or AsyncCacheBackend(
            prefix=DEFAULT_CACHE_PREFIX,
            default_ttl=DEFAULT_CACHE_TTL,
            redis_url=redis_url,
            redis_factory=redis_factory,
        )
        legacy_manager = legacy_cache_manager or manager
        self.cache_manager = manager
        self.legacy_manager = legacy_manager
        self.data_config = _NamespaceConfig(namespace=data_namespace, version=version)
        self.headers_config = _NamespaceConfig(namespace=headers_namespace, version=version)
        self.signature_config = _NamespaceConfig(namespace=signature_namespace, version=version)
        fallback_requested = any(
            value is not None
            for value in (version, data_namespace, headers_namespace, signature_namespace)
        ) or (legacy_cache_manager is not None and legacy_cache_manager is not manager)
        self._fallback_enabled = fallback_to_legacy and fallback_requested
        self.redis_url = redis_url or settings.redis_url
        self.redis_factory = redis_factory

    def _marketplace_key(
        self,
        marketplace: Optional[str],
        *,
        include_version: bool = True,
        include_namespace: bool = True,
    ) -> str:
        """ Normaliza a chave do marketplace aplicando namespace e versão """
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
        """ Aplica namespace e versão à URL informada """
        return config.apply(
            url,
            include_namespace=include_namespace,
            include_version=include_version,
        )
    
    async def get(self, *, marketplace: str | None, url: str) -> Optional[Dict[str, Any]]:
        """ Busca um item no cache, recorrendo ao namespace legado se necessário """
        value = await self.cache_manager.get(
            marketplace=self._marketplace_key(marketplace),
            url=url,
        )
        if value is not None or not self._fallback_enabled:
            return value
        return await self.legacy_manager.get(
            marketplace=self._marketplace_key(
                marketplace,
                include_namespace=False,
                include_version=False,
            ),
            url=url,
        )
    
    async def set(
        self,
        *,
        marketplace: str | None,
        url: str,
        value: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> None:
        """ Persiste o valor utilizando namespace atual e replica no legado opcionalmente """
        await self.cache_manager.set(
            marketplace=self._marketplace_key(marketplace),
            url=url,
            value=value,
            ttl=ttl,
        )
        if self._fallback_enabled:
            await self.legacy_manager.set(
                marketplace=self._marketplace_key(
                    marketplace,
                    include_namespace=False,
                    include_version=False,
                ),
                url=url,
                value=value,
                ttl=ttl,
            )

    async def touch(
        self,
        *,
        marketplace: str | None,
        url: str,
        ttl: Optional[int] = None,
    ) -> None:
        """ Renova o TTL da chave ativa de do namespace legado, quando disponível """
        await self.cache_manager.touch(
            marketplace=self._marketplace_key(marketplace),
            url=url,
            ttl=ttl,
        )
        if self._fallback_enabled:
            await self.legacy_manager.touch(
                marketplace=self._marketplace_key(
                    marketplace,
                    include_namespace=False,
                    include_version=False,
                ),
                url=url,
                ttl=ttl,
            )

    async def _get_raw_redis(self) -> redis.Redis | None:
        """ Acessa diretamente o Redis para operações específicas (headers e assinatura) """
        backend = self.cache_manager
        if isinstance(backend, AsyncCacheBackend):
            return await backend._get_redis()
        if self.redis_factory is not None:
            candidate = self.redis_factory()
            if inspect.isawaitable(candidate):
                return await candidate
            return candidate
        try:
            return redis.Redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=False,
            )
        except Exception as err:
            logger.warning(
                "initialize_redis_async_failed",
                error=sanitize_log_data(str(err)),
            )
            return None
        
    async def get_headers(self, url: str) -> Dict[str, Optional[str]]:
        """ Recupera cabeçalhos condicionais aplicando fallback para namespace legado """
        versioned_url = self._url_key(url, config=self.headers_config)
        headers = await self._get_headers_for_key(versioned_url)
        if self._fallback_enabled and not any(headers.values()):
            legacy_url = self._url_key(
                url,
                config=self.headers_config,
                include_namespace=False,
                include_version=False,
            )
            return await self._get_headers_for_key(legacy_url)
        return headers
    
    async def _get_headers_for_key(self, key_url: str) -> Dict[str, Optional[str]]:
        """ Função auxiliar para recuperar cabeçalhos no Redis """
        client = await self._get_raw_redis()
        if client is None:
            return {"etag": None, "last_modified": None}
        try:
            url_hash = _hash_url(key_url)
            etag = await client.get(f"{DEFAULT_ETAG_PREFIX}{url_hash}")
            last_modified = await client.get(f"{DEFAULT_LAST_MODIFIED_PREFIX}{url_hash}")
            if isinstance(etag, bytes):
                etag = etag.decode("utf-8")
            if isinstance(last_modified, bytes):
                last_modified = last_modified.decode("utf-8")
            return {"etag": etag, "last_modified": last_modified}
        except Exception as err:
            logger.warning(
                "retrieve_headers_failed",
                url=key_url,
                error=sanitize_log_data(str(err)),
            )
            return {"etag": None, "last_modified": None}

    async def store_headers(
        self,
        url: str,
        *,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        ttl_seconds: int | None = None,
    ) -> None:
        """ Persiste cabeçalhos HTTP considerando namespace atual e opcionalmente o legado """
        versioned_url = self._url_key(url, config=self.headers_config)
        await self._store_headers_for_key(
            versioned_url,
            etag=etag,
            last_modified=last_modified,
            ttl_seconds=ttl_seconds,
        )
        if self._fallback_enabled and self._write_legacy_headers:
            legacy_url = self._url_key(
                url,
                config=self.headers_config,
                include_namespace=False,
                include_version=False,
            )
            await self._store_headers_for_key(
                legacy_url,
                etag=etag,
                last_modified=last_modified,
                ttl_seconds=ttl_seconds,
            )

    async def _store_headers_for_key(
        self,
        url: str,
        *,
        etag: Optional[str],
        last_modified: Optional[str],
        ttl_seconds: int | None,
    ) -> None:
        """ Auxiliar que grava cabeçalhos utilizando o Redis assíncrono """
        client = await self._get_raw_redis()
        if client is None:
            return
        ttl = ttl_seconds if ttl_seconds is not None else settings.ETAG_CACHE_TTL
        url_hash = _hash_url(url)
        try:
            if etag is not None:
                await client.set(f"{DEFAULT_ETAG_PREFIX}{url_hash}", etag, ex=ttl)
            if last_modified is not None:
                await client.set(
                    f"{DEFAULT_LAST_MODIFIED_PREFIX}{url_hash}",
                    last_modified,
                    ex=ttl,
                )
        except Exception as err:
            logger.warning(
                "store_headers_failed",
                url=url,
                error=sanitize_log_data(str(err)),
            )

    async def check_or_update_signature(
        self,
        url: str,
        html: str,
    ) -> Any:
        """ Verifica se o conteúdo mudou e atualiza a assinatura conforme necessário """
        if self._fallback_enabled:
            legacy_result = await self._check_signature_for_key(
                self._url_key(
                    url,
                    config=self.signature_config,
                    include_namespace=False,
                    include_version=False,
                ),
                html,
                update_if_not_modified=True,
            )
            if legacy_result is NOT_MODIFIED:
                await self._check_signature_for_key(
                    self._url_key(url, config=self.signature_config),
                    html,
                    update_if_not_modified=False,
                )
                return NOT_MODIFIED
        return await self._check_signature_for_key(
            self._url_key(url, config=self.signature_config),
            html,
            update_if_not_modified=True,
        )
    
    async def _check_signature_for_key(
        self,
        url: str,
        html: str,
        *,
        update_if_not_modified: bool,
    ) -> Any:
        """ Manipula assinaturas de conteúdo para a chave informada """
        signature = hashlib.sha256(html.encode("utf-8")).hexdigest()
        client = await self._get_raw_redis()
        if client is None:
            return signature
        key = f"{DEFAULT_SIGNATURE_PREFIX}{_hash_url(url)}"
        try:
            previous = await client.get(key)
            if isinstance(previous, bytes):
                previous = previous.decode("utf-8")
            if previous == signature:
                if update_if_not_modified:
                    await client.set(key, signature, ex=settings.SIG_CACHE_TTL)
                return NOT_MODIFIED
            await client.set(key, signature, ex=settings.SIG_CACHE_TTL)
            return signature
        except Exception as err:
            logger.warning(
                "signature_content_failed",
                url=url,
                error=sanitize_log_data(str(err)),
            )
            return signature

def _load_namespace(env_name: str) -> Optional[str]:
    """ Carrega valores de namespace das variáveis de ambiente """
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

__all__ = [
    "CacheAdapter", 
    "cache_adapter", 
    "NOT_MODIFIED",
    "AsyncCacheBackend",    
]
