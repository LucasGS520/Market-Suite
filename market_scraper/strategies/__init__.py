""" Pacote de estratégias de scraping """

from .base import ScrapingStrategy
from .playwright_default import PlaywrightDefaultStrategy


__all__ = [
    "ScrapingStrategy",
    "PlaywrightDefaultStrategy",
]
