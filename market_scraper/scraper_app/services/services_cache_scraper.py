""" Funções compartilhadas para o fluxo de scraping

Este módulo concentra a lógica de reaproveitamento de cache com base no
hash do HTML. Identificamos alterações de conteúdo e reutilizamos os
dados armazenados em Redis sempre que o HTML não mudou para reduzir
requisições desnecessárias.
"""

from __future__ import annotations

from typing import Callable, Optional, Any

from utils.circuit_breaker import CircuitBreaker

import structlog

from scraper_app.utils.intelligent_cache import IntelligentCacheManager
from scraper_app.core.config import settings
from scraper_app.utils.audit_logger import audit_scrape
from alert_app.metrics import (
    CACHE_HITS_TOTAL, CACHE_MISSES_TOTAL,
    CACHE_HITS_ENDPOINT_TOTAL, CACHE_MISSES_ENDPOINT_TOTAL
)


logger = structlog.get_logger("scraper_common")
cache_manager = IntelligentCacheManager(base_ttl=settings.CACHE_BASE_TTL)

def use_cache_if_not_modified(
    target_url: str,
    html: str | None,
    payload,
    persist_fn: Callable[[dict], Any] | None,
    circuit_breaker: CircuitBreaker,
    circuit_key: str,
    id_key: str,
    endpoint: str | None = None
) -> Optional[dict]:
    """ Retorna dados do cache quando o HTML não sofreu alterações

    Quando ``persist_fn`` é informada, cabe ao chamador realizar
    persistência dos dados do cache
    """
    cached = cache_manager.get(target_url)
    if not cached or html is None:
        CACHE_MISSES_TOTAL.inc()
        if endpoint:
            CACHE_MISSES_ENDPOINT_TOTAL.labels(endpoint=endpoint).inc()
        return None

    new_hash = cache_manager._hash_content(html)
    if cached.get("hash") == new_hash:
        CACHE_HITS_TOTAL.inc()
        if endpoint:
            CACHE_HITS_ENDPOINT_TOTAL.labels(endpoint=endpoint).inc()
        audit_scrape(
            stage="cache",
            url=target_url,
            payload=payload.model_dump(),
            html=None,
            details=cached.get("data", {}),
            error=None
        )
        circuit_breaker.record_success(circuit_key)
        logger.info("cache_hit", url=target_url)
        if persist_fn:
            new_id = persist_fn(cached.get("data", {}))
            return {"status": "cached", id_key: str(new_id)}
        return {"status": "cached", "details": cached.get("data", {})}

    CACHE_MISSES_TOTAL.inc()
    if endpoint:
        CACHE_MISSES_ENDPOINT_TOTAL.labels(endpoint=endpoint).inc()
    logger.info("cache_miss_after_hash", url=target_url)
    return None

def update_cache(target_url: str, data: dict, html: str, etag: str | None) -> None:
    """ Persistem no cache o HTML e os dados recém extraídos """
    cache_manager.set(target_url, data, html, etag=etag)
