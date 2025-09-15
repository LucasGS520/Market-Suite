""" Camada de serviços que orquestra lógica de negócio

Este pacote expõe funções utilitárias para scraping e demais
operações de suporte à aplicação principal. Também disponibiliza
as etapas e pipelines sinérgicos definidos para coleta multilayer.
"""

from .services_scraper_common import scrape_product_common, scrape_product_common_async
from .pipeline_steps import (
    MechanicalSoupLoginStep,
    ExtructExtractionStep,
    ParselExtractionStep,
    BeautifulSoupExtractionStep,
    RequestsHTMLRenderStep,
    SelectorLibExtractionStep,
)
from .synergic_scraper_pipeline import SynergicScraperPipeline


__all__ = [
    "scrape_product_common", 
    "scrape_product_common_async",
    "MechanicalSoupLoginStep",
    "ExtructExtractionStep",
    "ParselExtractionStep",
    "BeautifulSoupExtractionStep",
    "RequestsHTMLRenderStep",
    "SelectorLibExtractionStep",
    "SynergicScraperPipeline",
]
