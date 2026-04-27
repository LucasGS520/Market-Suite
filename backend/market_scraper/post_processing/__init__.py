"""Camada de Post-Processing do market_scraper.

Expõe o processador unificado, normalizers e DTOs.

Factory:
    get_post_processor() → PostProcessor (instância nova; stateless)
"""

from __future__ import annotations

from market_scraper.post_processing.processor import PostProcessor
from market_scraper.post_processing.normalizers.price_normalizer import PriceNormalizer
from market_scraper.post_processing.normalizers.product_normalizer import ProductNormalizer
from market_scraper.domain.dtos import PostProcessResult


def get_post_processor() -> PostProcessor:
    """Retorna instância de PostProcessor (stateless, criada a cada chamada)."""
    return PostProcessor()


__all__ = [
    "PostProcessor",
    "get_post_processor",
    "PriceNormalizer",
    "ProductNormalizer",
    "PostProcessResult",
]
