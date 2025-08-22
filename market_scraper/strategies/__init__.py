""" Pacote de estratégias de scraping """

from .base import ScrapingStrategy, register_strategy, get_strategy_for_url

#Importa estratégias concretas para registro
from . import playwright_default

__all__ = [
    "ScrapingStrategy",
    "register_strategy",
    "get_strategy_for_url",
]
