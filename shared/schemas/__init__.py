""" Exporta esquemas Pydantic compartilhados entre os serviços

Este módulo centraliza as exportações de esquemas utilizados por
diferentes componentes do projeto, facilitando sua reutilização
"""

from .schemas_products import MonitoredProductCreateScraping, MonitoredScrapedInfo, CompetitorProductCreateScraping, CompetitorScrapedInfo
from .schemas_scraper import ScraperRequest, ScraperResponse


__all__ = [
    "MonitoredProductCreateScraping",
    "MonitoredScrapedInfo",
    "CompetitorProductCreateScraping",
    "CompetitorScrapedInfo",
    "ScraperRequest",
    "ScraperResponse",
]
