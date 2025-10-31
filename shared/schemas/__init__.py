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
    ScrapeResult,
)


__all__ = [
    "MonitoredProductCreateScraping",
    "MonitoredScrapedInfo",
    "CompetitorProductCreateScraping",
    "CompetitorScrapedInfo",
    "ParserRequest",
    "ParserResponse",
    "ScrapeResult",
]
