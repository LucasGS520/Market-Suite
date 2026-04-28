"""Camada de Collection do market_scraper.

Expõe contratos, implementações e factory functions do runtime de coleta.

Factory functions:
    get_collection_policy() → ResponseClassifierPolicy
    get_crawlee_runtime()   → CrawleeRuntime (singleton)
"""

from __future__ import annotations

from market_scraper.collection.collectors.browser_collector import PlaywrightBrowserCollector
from market_scraper.collection.collectors.http_collector import HttpCollector
from market_scraper.collection.collectors.protocols import BrowserCollector
from market_scraper.collection.crawler.crawlee_runtime import CrawleeRuntime
from market_scraper.collection.dto.collected_document import CollectedDocument
from market_scraper.collection.dto.collection_attempt import CollectionAttempt
from market_scraper.collection.policy import (
    CollectionDecision,
    CollectionPolicyAction,
    ResponseClassifierPolicy,
)


def get_collection_policy() -> ResponseClassifierPolicy:
    """Retorna a política de classificação de coleção (stateless)."""
    return ResponseClassifierPolicy()


# Singleton do runtime de coleta — lifecycle gerenciado via startup()/shutdown() em main.py
crawlee_runtime = CrawleeRuntime()


def get_crawlee_runtime() -> CrawleeRuntime:
    """Retorna o singleton de coleta Crawlee (HTTP primário + browser fallback)."""
    return crawlee_runtime


__all__ = [
    "BrowserCollector",
    "CollectedDocument",
    "HttpCollector",
    "CollectionAttempt",
    "CollectionDecision",
    "CollectionPolicyAction",
    "CrawleeRuntime",
    "PlaywrightBrowserCollector",
    "ResponseClassifierPolicy",
    "crawlee_runtime",
    "get_collection_policy",
    "get_crawlee_runtime",
]
