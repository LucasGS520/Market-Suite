""" Agrupa parsers de HTML e dados estruturados utilizados no scraper """

from .html_static import (
    parse_generic_html,
    parse_meli_html,
    parse_amazon_html,
    parse_magalu_html,
)
from .extruct import parse_with_extruct
from .parsel import parse_with_parsel
from .beautifulsoup import parse_with_beautifulsoup
from .selectorlib import load_selectorlib_extractor, parse_with_selectorlib

__all__ = [
    "parse_generic_html",
    "parse_meli_html",
    "parse_amazon_html",
    "parse_magalu_html",
    "parse_with_extruct",
    "parse_with_parsel",
    "parse_with_beautifulsoup",
]
