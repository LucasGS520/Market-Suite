""" Pacote de estratégias de scraping """

from .base import ScrapingStrategy
from .html_static import (
    HtmlStaticStrategy,
    MercadoLivreHtmlStaticStrategy,
    AmazonHtmlStaticStrategy,
    ShopeeHtmlStaticStrategy,
    MagaluHtmlStaticStrategy,
)
from .json_endpoint import (
    JsonEndpointStrategy,
    MercadoLivreJsonStrategy,
    AmazonJsonStrategy,
    ShopeeJsonStrategy,
    MagaluJsonStrategy,
)


__all__ = [
    "ScrapingStrategy",
    "HtmlStaticStrategy",
    "MercadoLivreHtmlStaticStrategy",
    "AmazonHtmlStaticStrategy",
    "ShopeeHtmlStaticStrategy",
    "MagaluHtmlStaticStrategy",
    "JsonEndpointStrategy",
    "MercadoLivreJsonStrategy",
    "AmazonJsonStrategy",
    "ShopeeJsonStrategy",
    "MagaluJsonStrategy",
]
