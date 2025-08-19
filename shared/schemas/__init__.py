""" Exporta esquemas Pydantic compartilhados de produtos

Este módulo centraliza as exportações de esquemas utilizados por
diferentes componentes do projeto, facilitando sua reutilização
"""

from .products import MonitoredProductCreateScraping, MonitoredScrapedInfo, CompetitorProductCreateScraping, CompetitorScrapedInfo


__all__ = [
    "MonitoredProductCreateScraping",
    "MonitoredScrapedInfo",
    "CompetitorProductCreateScraping",
    "CompetitorScrapedInfo",
]
