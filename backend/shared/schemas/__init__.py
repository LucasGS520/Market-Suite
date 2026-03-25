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
from .shared_schemas_orchestrator import (
    CollectionPayload,
    validate_payload,
    DispatchActivityOutput,
    QueryStatusOutput,
    PolicyActivityOutput,
    WorkflowStateSnapshot,
    CollectionResult,
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
    "CollectionPayload",
    "validate_payload",
    "DispatchActivityOutput",
    "QueryStatusOutput",
    "PolicyActivityOutput",
    "WorkflowStateSnapshot",
    "CollectionResult",
]
