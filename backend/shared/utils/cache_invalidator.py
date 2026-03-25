""" Utilitários de invalidação de cache para pontos de escrita

Fornece funções direcionadas para invalidar o cache Redis após operações
que alteram dados persistentes em PostgreSQL. Deve ser chamado após
commits bem-sucedidos para garantir que o cache reflita o estado atual.

Uso típico (após commit no banco):
    from shared.utils.cache_invalidator import invalidate_product_cache

    def create_for_monitored(db, ...):
        # ... insere PriceHistory ...
        db.commit()
        invalidate_product_cache(monitored_product_id)
"""

from __future__ import annotations

import structlog

from shared.enums.cache_keys import CacheKey
from shared.infra.cache_strategy import invalidate, invalidate_pattern


logger = structlog.get_logger(__name__)

def invalidate_product_cache(product_id: int | str) -> None:
    """Invalida todo o cache de um produto monitorado.

    Deve ser chamado após qualquer escrita que afete:
      - current_price em MonitoredProduct
      - inserção em PriceHistory
      - inserção em PriceComparison / PriceComparisonSummary

    Usa SCAN com padrão ``cache:product:{id}:*`` para cobrir
    preço, comparação e lista de concorrentes em uma única chamada.
    """
    pattern = CacheKey.product_all_pattern(product_id)
    logger.debug("invalidating_product_cache", product_id=product_id, pattern=pattern)
    invalidate_pattern(pattern)

def invalidate_product_price(product_id: int | str) -> None:
    """Invalida apenas o cache de preço de um produto monitorado."""
    invalidate(CacheKey.product_price(product_id))

def invalidate_product_comparison(product_id: int | str) -> None:
    """Invalida o cache de resumo de comparação de um produto monitorado."""
    invalidate(CacheKey.product_comparison(product_id))

def invalidate_robots(host: str) -> None:
    """Invalida o cache de robots.txt de um host específico."""
    invalidate(CacheKey.robots_txt(host))


__all__ = [
    "invalidate_product_cache",
    "invalidate_product_price",
    "invalidate_product_comparison",
    "invalidate_robots",
]
