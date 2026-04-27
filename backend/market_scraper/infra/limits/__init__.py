"""Infraestrutura de limites de taxa e concorrência."""

from market_scraper.infra.limits.adaptive_rate_limiter import adaptive_rate_limiter
from market_scraper.infra.limits.concurrency_limits import browser_semaphore

__all__ = ["adaptive_rate_limiter", "browser_semaphore"]
