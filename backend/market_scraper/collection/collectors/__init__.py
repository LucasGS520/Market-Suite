"""Implementações concretas de coletores browser."""

from market_scraper.collection.collectors.browser_collector import PlaywrightBrowserCollector
from market_scraper.collection.collectors.protocols import BrowserCollector

__all__ = [
    "BrowserCollector",
    "PlaywrightBrowserCollector",
]
