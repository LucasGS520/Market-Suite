""" Pacote de estratégias de scraping """

from .base import ScrapingStrategy
from .html_static import (
    parse_generic_html,
    parse_meli_html,
    parse_amazon_html,
    parse_magalu_html,
)
from .extruct_parser import parse_with_extruct
from .parsel_parser import parse_with_parsel
from .beautifulsoup_html import parse_with_beautifulsoup
from .requests_html import parse_with_requests_html
from .selectorlib_strategy import parse_with_selectorlib


__all__ = [
    "ScrapingStrategy",
    "parse_generic_html",
    "parse_meli_html",
    "parse_amazon_html",
    "parse_magalu_html",
    "parse_with_extruct",
    "parse_with_parsel",
    "parse_with_beautifulsoup",
    "parse_with_requests_html",
    "parse_with_selectorlib",
]
