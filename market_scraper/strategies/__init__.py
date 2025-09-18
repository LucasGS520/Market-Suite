""" Pacote de estratégias de scraping """

from .base import ScrapingStrategy
from .html_static import (
    parse_generic_html,
    parse_meli_html,
    parse_amazon_html,
    parse_magalu_html,
)
from .selectorlib_strategy import SelectorLibStrategy


__all__ = [
    "ScrapingStrategy",
    "parse_generic_html",
    "parse_meli_html",
    "parse_amazon_html",
    "parse_magalu_html",
    "HtmlStaticStrategy",
    "MercadoLivreHtmlStaticStrategy",
    "AmazonHtmlStaticStrategy",
    "MagaluHtmlStaticStrategy",
    "SelectorLibStrategy",
]
