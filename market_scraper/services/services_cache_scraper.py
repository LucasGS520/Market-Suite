""" Funções compartilhadas para o fluxo de scraping

Este módulo concentra a lógica de reaproveitamento de cache com base no
hash do HTML. Identificamos alterações de conteúdo e reutilizamos os
dados armazenados em Redis sempre que o HTML não mudou para reduzir
requisições desnecessárias.
"""

from __future__ import annotations

from typing import Optional

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
    circuit_breaker: CircuitBreaker,
    circuit_key: str,
    endpoint: str | None = None
) -> Optional[dict]:
    """ Retorna dados armazenados em cache quando o HTML não mudou

    A função não executa nenhuma persistência externa, limitando-se
    a responder com dados já existentes em memória
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
        return {"status": "cached", "details": cached.get("data", {})}

    CACHE_MISSES_TOTAL.inc()
    if endpoint:
        CACHE_MISSES_ENDPOINT_TOTAL.labels(endpoint=endpoint).inc()
    logger.info("cache_miss_after_hash", url=target_url)
    return None

def update_cache(target_url: str, data: dict, html: str, etag: str | None) -> None:
    """ Persistem no cache o HTML e os dados recém extraídos """
    cache_manager.set(target_url, data, html, etag=etag)
