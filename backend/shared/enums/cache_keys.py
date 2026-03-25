""" Templates de chaves Redis para padrão Cache-Aside

Centraliza todos os padrões de chave usados para caching de dados de negócio.
Prefixo `cache:` diferencia de chaves de controle (lock:, rate:, circuit:, idemp:).

Convenção:
  cache:{entidade}:{id}:{dado}
"""

from __future__ import annotations


class CacheKey:
    """Factories de chave para cache de dados de negócio."""

    # Preço atual do produto monitorado
    # TTL: REDIS_TTL_CACHE_DATA_SECONDS (300s)
    PRODUCT_CURRENT_PRICE = "cache:product:{product_id}:price"

    # Resumo de comparação mais recente de um produto monitorado
    # TTL: REDIS_TTL_CACHE_DATA_SECONDS (300s)
    PRODUCT_COMPARISON_SUMMARY = "cache:product:{product_id}:comparison"

    # Lista de concorrentes de um produto monitorado
    # TTL: REDIS_TTL_CACHE_DATA_SECONDS (300s)
    PRODUCT_COMPETITORS = "cache:product:{product_id}:competitors"

    # Conteúdo do robots.txt por host (usado pelo market_scraper)
    # TTL: REDIS_TTL_ROBOTS_CACHE_SECONDS (3600s)
    ROBOTS_TXT = "robots:{host}"

    @staticmethod
    def product_price(product_id: int | str) -> str:
        return CacheKey.PRODUCT_CURRENT_PRICE.format(product_id=product_id)

    @staticmethod
    def product_comparison(product_id: int | str) -> str:
        return CacheKey.PRODUCT_COMPARISON_SUMMARY.format(product_id=product_id)

    @staticmethod
    def product_competitors(product_id: int | str) -> str:
        return CacheKey.PRODUCT_COMPETITORS.format(product_id=product_id)

    @staticmethod
    def robots_txt(host: str) -> str:
        return CacheKey.ROBOTS_TXT.format(host=host)

    @staticmethod
    def product_all_pattern(product_id: int | str) -> str:
        """Padrão SCAN para invalidar todos os caches de um produto."""
        return f"cache:product:{product_id}:*"


__all__ = ["CacheKey"]
