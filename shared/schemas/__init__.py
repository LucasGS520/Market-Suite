""" Exporta esquemas Pydantic compartilhados entre os serviços """

from .schemas_products import (
    MonitoredProductCreateScraping,
    MonitoredScrapedInfo,
    CompetitorProductCreateScraping,
    CompetitorScrapedInfo,
)
from .schemas_scraper import (
    ParserRequest,
    ParserResponse,
    ScraperRequest,
    ScraperResponse,
)


__all__ = [
    "MonitoredProductCreateScraping",
    "MonitoredScrapedInfo",
    "CompetitorProductCreateScraping",
    "CompetitorScrapedInfo",
    "ScraperRequest",
    "ScraperResponse",
]
