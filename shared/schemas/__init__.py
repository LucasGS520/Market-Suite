""" Exporta esquemas Pydantic compartilhados entre os serviços """

from .schemas_products import (
    MonitoredProductCreateScraping,
    MonitoredScrapedInfo,
    CompetitorProductCreateScraping,
    CompetitorScrapedInfo,
)
from .schemas_scraper import ScraperRequest, ScraperResponse
from .schemas_scraper import ParseRequest, ParseResponse


__all__ = [
    "MonitoredProductCreateScraping",
    "MonitoredScrapedInfo",
    "CompetitorProductCreateScraping",
    "CompetitorScrapedInfo",
    "ScraperRequest",
    "ScraperResponse",
    "ParseRequest",
    "ParseResponse",
]
