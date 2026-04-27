""" Implementações concretas de coletores HTTP e browser. """

from market_scraper.collection.collectors.browser_collector import PlaywrightBrowserCollector
from market_scraper.collection.collectors.http_collector import CurlCFFIHttpCollector
from market_scraper.collection.collectors.protocols import BrowserCollector, HttpCollector

__all__ = [
    "HttpCollector",
    "BrowserCollector",
    "CurlCFFIHttpCollector",
    "PlaywrightBrowserCollector",
]
