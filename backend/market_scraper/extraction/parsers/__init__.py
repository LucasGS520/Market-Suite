""" Parsers de HTML da camada de extração """

from .extruct import parse_with_extruct
from .parsel import parse_with_parsel
from .beautifulsoup import parse_with_beautifulsoup

__all__ = [
    "parse_with_extruct",
    "parse_with_parsel",
    "parse_with_beautifulsoup",
]
