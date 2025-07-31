""" Funções compartilhadas para o fluxo de scraping

Este módulo concentra a lógica de reaproveitamento de cache com base no
hash do HTML. Identificamos alterações de conteúdo e reutilizamos os
dados armazenados em Redis sempre que o HTML não mudou para reduzir
requisições desnecessárias.
"""

from __future__ import annotations

from typing import Callable, Optional, Any

from app.utils.circuit_breaker import CircuitBreaker

import structlog
from sqlalchemy.orm import Session

from app.utils.intelligent_cache import IntelligentCacheManager
from app.core.config import settings
from app.utils.audit_logger import audit_scrape
from app.metrics import (
    CACHE_HITS_TOTAL, CACHE_MISSES_TOTAL,
    CACHE_HITS_ENDPOINT_TOTAL, CACHE_MISSES_ENDPOINT_TOTAL
)


logger = structlog.get_logger("scraper_common")
cache_manager = IntelligentCacheManager(base_ttl=settings.CACHE_BASE_TTL)

def use_cache_if_not_modified(
    db: Session,
    target_url: str,
    html: str | None,
    payload,
    persist_fn: Callable[[dict], Any],
    circuit_breaker: CircuitBreaker,
    circuit_key: str,
    id_key: str,
    endpoint: str | None = None
) -> Optional[dict]:
    """ Retorna dados do cache quando o HTML não sofreu alterações

    Parametros
    ----------
    db: Session
        Sessão do banco para persistência
    target_url: str
        URL utilizada como chave de cache.
    payload: BaseModel
        Dados originais usados no scraping
    persist_fn: Callable[[dict], Any]
        Função que salva os dados do cache e retorna o identificador
        (product_id ou competitor_id)
    circuit_breaker: CircuitBreaker
        Circuit breaker do fluxo
    circuit_key: str
        Chave para registro no circuit breaker
    id_key: str
        Nome do campo retornado ("product_id" ou "competitor_id")
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
        new_id = persist_fn(cached.get("data", {}))
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
        return {"status": "cached", id_key: str(new_id)}

    CACHE_MISSES_TOTAL.inc()
    if endpoint:
        CACHE_MISSES_ENDPOINT_TOTAL.labels(endpoint=endpoint).inc()
    logger.info("cache_miss_after_hash", url=target_url)
    return None

def update_cache(target_url: str, data: dict, html: str, etag: str | None) -> None:
    """ Persistem no cache o HTML e os dados recém extraídos """
    cache_manager.set(target_url, data, html, etag=etag)
