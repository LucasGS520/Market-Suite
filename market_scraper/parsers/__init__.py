""" Conjunto de parsers puros para o serviço ``market_scraper`` 

Cada módulo implementa extrações específicas utilizando bibliotecas
distintas (BeautifulSoup, Parsel, Extruct, Requests-HTML, SelectorLib).
Todos recebem HTML bruto (e opcionalmente a URL original) e retornam
um dicionário padronizado com ``name``, ``current_price`` e ``url``.
O pipeline e as estratégias apenas orquestram esses parsers.
"""

from .html_static import (
    parse_generic_html,
    parse_meli_html,
    parse_amazon_html,
    parse_magalu_html,
)
from .extruct import parse_with_extruct
from .parsel import parse_with_parsel
from .beautifulsoup import parse_with_beautifulsoup
from .requests_html import parse_with_requests_html
from .selectorlib import load_selectorlib_extractor, parse_with_selectorlib

__all__ = [
    "parse_generic_html",
    "parse_meli_html",
    "parse_amazon_html",
    "parse_magalu_html",
    "parse_with_extruct",
    "parse_with_parsel",
    "parse_with_beautifulsoup",
    "parse_with_requests_html",
    "load_selectorlib_extractor",
    "parse_with_selectorlib",
]
