""" Controle de concorrência para recursos externos do market_scraper.

Estratégia em duas camadas:
1. **Crawlee ConcurrencySettings** — controle primário para o crawler HTTP/browser;
   configurado no CrawleeRuntime e delega autoscaling ao próprio Crawlee.
2. **asyncio.Semaphore** — controle de recursos externos que o Crawlee não
   gerencia diretamente, como o pool de browser compartilhado (PlaywrightPool).

Este módulo expõe apenas o segundo tipo, já que o primeiro vive no runtime.

Uso:

    from market_scraper.infra.limits.concurrency_limits import browser_semaphore

    async with browser_semaphore:
        html = await browser_pool.fetch_html(url)
"""

from __future__ import annotations

import asyncio
import os


def browser_limit() -> int:
    """Retorna o limite canonico de contexts Playwright simultaneos."""
    return int(os.getenv("PLAYWRIGHT_MAX_CONCURRENT", "5"))


def create_browser_semaphore(max_concurrent: int | None = None) -> asyncio.Semaphore:
    """Cria semaphore de browser a partir da fonte canonica de limite."""
    return asyncio.Semaphore(max_concurrent if max_concurrent is not None else browser_limit())


browser_semaphore: asyncio.Semaphore = create_browser_semaphore()
"""Semaphore que limita contextos Playwright simultâneos.

O valor é lido de PLAYWRIGHT_MAX_CONCURRENT em tempo de importação.
Já é usado internamente pelo PlaywrightPool; este export torna a intenção
explícita para código que precise coordenar acesso externo ao pool.
"""


__all__ = ["browser_limit", "browser_semaphore", "create_browser_semaphore"]
