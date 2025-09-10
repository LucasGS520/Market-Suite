""" Pacote de estratégias de scraping """

from .base import ScrapingStrategy
from .html_static import (
    HtmlStaticStrategy,
    MercadoLivreHtmlStaticStrategy,
    AmazonHtmlStaticStrategy,
    MagaluHtmlStaticStrategy,
)
from .json_endpoint import (
    JsonEndpointStrategy,
    MercadoLivreJsonStrategy,
    AmazonJsonStrategy,
    MagaluJsonStrategy,
)


__all__ = [
    "ScrapingStrategy",
    "HtmlStaticStrategy",
    "MercadoLivreHtmlStaticStrategy",
    "AmazonHtmlStaticStrategy",
    "MagaluHtmlStaticStrategy",
    "JsonEndpointStrategy",
    "MercadoLivreJsonStrategy",
    "AmazonJsonStrategy",
    "MagaluJsonStrategy",
]
