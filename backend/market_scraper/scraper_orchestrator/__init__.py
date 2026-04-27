""" Orquestrador canônico do market_scraper.

Expõe o caso de uso principal de scraping, a fachada pública e os tipos de resultado.
"""

from market_scraper.scraper_orchestrator.parse_product import (
    ParseProduct,
    ParseProductError,
    ParseProductNoResult,
    ParseProductResult,
    ParseProductSuccess,
)
from market_scraper.scraper_orchestrator.orchestrator import (
    ScraperOrchestrator,
    get_scraper_orchestrator,
)

__all__ = [
    "ParseProduct",
    "ParseProductError",
    "ParseProductNoResult",
    "ParseProductResult",
    "ParseProductSuccess",
    "ScraperOrchestrator",
    "get_scraper_orchestrator",
]
