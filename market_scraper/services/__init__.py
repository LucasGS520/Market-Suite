""" Camada de serviços que orquestra lógica de negócio

Este pacote expõe funções utilitárias para scraping e demais
operações de suporte à aplicação principal.
"""

from .services_scraper_common import scrape_product_common, scrape_product_common_async

__all__ = ["scrape_product_common", "scrape_product_common_async"]
