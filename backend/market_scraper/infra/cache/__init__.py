"""Infraestrutura de cache (condicional, singleflight, robots e TTL)."""

from market_scraper.infra.cache import cache, singleflight

__all__ = ["cache", "singleflight"]
