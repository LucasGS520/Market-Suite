""" Pacote de estratégias de scraping """

from .base import ScrapingStrategy
from .playwright_default import PlaywrightDefaultStrategy
from .html_static import (
    HtmlStaticStrategy,
    MercadoLivreHtmlStaticStrategy,
    AmazonHtmlStaticStrategy,
    ShopeeHtmlStaticStrategy,
    MagaluHtmlStaticStrategy,
)


__all__ = [
    "ScrapingStrategy",
    "PlaywrightDefaultStrategy",
    "HtmlStaticStrategy",
    "MercadoLivreHtmlStaticStrategy",
    "AmazonHtmlStaticStrategy",
    "ShopeeHtmlStaticStrategy",
    "MagaluHtmlStaticStrategy",
]
