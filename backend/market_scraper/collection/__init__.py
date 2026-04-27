"""Camada de Collection do market_scraper.

Expõe contratos (protocolos), implementações concretas e factory functions.

Factory functions:
    get_http_collector()    → CurlCFFIHttpCollector
    get_browser_collector() → PlaywrightBrowserCollector
    get_collection_policy() → ResponseClassifierPolicy
    get_crawlee_runtime()   → CrawleeRuntime
"""

from __future__ import annotations

from market_scraper.collection.collectors.browser_collector import PlaywrightBrowserCollector
from market_scraper.collection.collectors.http_collector import CurlCFFIHttpCollector
from market_scraper.collection.collectors.protocols import BrowserCollector, HttpCollector
from market_scraper.collection.crawler.crawlee_runtime import CrawleeRuntime
from market_scraper.collection.dto.collected_document import CollectedDocument
from market_scraper.collection.dto.collection_attempt import CollectionAttempt
from market_scraper.collection.policy import (
    CollectionDecision,
    CollectionPolicyAction,
    ResponseClassifierPolicy,
)
from market_scraper.utils.html_quality import is_html_useful


def get_http_collector() -> HttpCollector:
    """Retorna o HttpCollector padrão (curl_cffi)."""
    return CurlCFFIHttpCollector()


def get_browser_collector() -> BrowserCollector:
    """Retorna o BrowserCollector padrão (Playwright)."""
    return PlaywrightBrowserCollector()


def get_collection_policy() -> ResponseClassifierPolicy:
    """Retorna a política de classificação de coleção (stateless)."""
    return ResponseClassifierPolicy()


def get_crawlee_runtime() -> CrawleeRuntime:
    """Retorna o runtime de coleta padrão (HTTP + browser fallback)."""
    return CrawleeRuntime()


__all__ = [
    "BrowserCollector",
    "CollectedDocument",
    "CollectionAttempt",
    "CollectionDecision",
    "CollectionPolicyAction",
    "CrawleeRuntime",
    "CurlCFFIHttpCollector",
    "HttpCollector",
    "PlaywrightBrowserCollector",
    "ResponseClassifierPolicy",
    "get_browser_collector",
    "get_collection_policy",
    "get_crawlee_runtime",
    "get_http_collector",
    "is_html_useful",
]
