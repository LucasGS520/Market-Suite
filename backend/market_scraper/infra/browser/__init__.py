"""Infraestrutura de browser headless (pool Playwright)."""

from market_scraper.infra.browser.playwright_pool import playwright_pool

# Alias canônico: browser_pool é o nome de acesso preferido no novo código.
browser_pool = playwright_pool

__all__ = ["playwright_pool", "browser_pool"]
