"""Camada de Extraction do market_scraper.

Expõe a cadeia determinística de extração.

Factory:
    get_extraction_chain() → ExtractionChain (instância nova; stateless)
"""

from __future__ import annotations

from market_scraper.extraction.extraction_chain import ExtractionChain


def get_extraction_chain() -> ExtractionChain:
    """Retorna instância de ExtractionChain (stateless, criada a cada chamada)."""
    return ExtractionChain()


__all__ = [
    "ExtractionChain",
    "get_extraction_chain",
]
