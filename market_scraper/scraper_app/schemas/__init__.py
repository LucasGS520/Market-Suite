""" Esquemas Pydantic utilizados no serviço de scraping """

from .schemas_products import MonitoredProductCreateScraping, CompetitorProductCreateScraping


__all__ = [
    "MonitoredProductCreateScraping",
    "CompetitorProductCreateScraping",
]
