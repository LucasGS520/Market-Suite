""" Pacote de estratégias de scraping """

from .base import ScrapingStrategy
from .playwright_default import PlaywrightDefaultStrategy
from .json_endpoint import (
    JsonEndpointStrategy,
    MercadoLivreJsonEndpointStrategy,
    AmazonJsonEndpointStrategy,
    ShopeeJsonEndpointStrategy,
    MagaluJsonEndpointStrategy,
)


__all__ = [
    "ScrapingStrategy",
    "PlaywrightDefaultStrategy",
    "JsonEndpointStrategy",
    "MercadoLivreJsonEndpointStrategy",
    "AmazonJsonEndpointStrategy",
    "ShopeeJsonEndpointStrategy",
    "MagaluJsonEndpointStrategy",
]
