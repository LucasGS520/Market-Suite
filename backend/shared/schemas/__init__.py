""" Exporta esquemas Pydantic compartilhados entre os serviços """

from .shared_schemas_products import (
    ProductCore,
    MonitoredProductCreateScraping,
    MonitoredScrapedInfo,
    InitialCompetitorCreateScraping,
    CompetitorProductCreateScraping,
    CompetitorScrapedInfo,
)
from .shared_schemas_scraper import (
    ParserRequest,
    ParserResponse,
    ErrorResponse,
    ScrapeResult,
)


__all__ = [
    "MonitoredProductCreateScraping",
    "MonitoredScrapedInfo",
    "InitialCompetitorCreateScraping",
    "CompetitorProductCreateScraping",
    "CompetitorScrapedInfo",
    "ProductCore",
    "ParserRequest",
    "ParserResponse",
    "ErrorResponse",
    "ScrapeResult",
]
