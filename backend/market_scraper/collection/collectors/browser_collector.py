""" Implementação concreta de BrowserCollector via Playwright.

Encapsula playwright_pool sem expor detalhes de gerenciamento de pool
para a camada de orquestração. Exceções específicas do Playwright
(PlaywrightTimeoutError, etc.) propagam normalmente — o runtime de coleta
ou o use case as mapeia para erros canônicos de contrato.
"""

from __future__ import annotations

from market_scraper.infra.browser.playwright_pool import playwright_pool


class PlaywrightBrowserCollector:
    """ BrowserCollector usando o pool Playwright compartilhado do processo.

    Stateless — delega diretamente para o singleton playwright_pool.
    Gerenciamento de ciclo de vida (startup/shutdown) permanece em main.py.
    """

    @property
    def is_ready(self) -> bool:
        """ Indica se o pool de Playwright está disponível."""
        return playwright_pool.is_ready

    async def fetch(
        self,
        url: str,
        *,
        timeout: float,
        domain: str | None = None,
    ) -> str:
        """ Delega fetch_html ao playwright_pool preservando semântica de exceções."""
        return await playwright_pool.fetch_html(url, timeout=timeout, domain=domain)


__all__ = ["PlaywrightBrowserCollector"]
