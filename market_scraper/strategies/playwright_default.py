from __future__ import annotations

""" Estratégia padrão utilizando Playwright """

from typing import Any, Dict, Optional

from .base import ScrapingStrategy


class PlaywrightDefaultStrategy(ScrapingStrategy):
    """ Aplica o fluxo existente de scraping baseado em Playwright """

    priority = 100

    def supports_url(self, url: str) -> bool:
        """ Suporta qualquer URL por padrão """
        return True

    async def get_data(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> dict:
        """ Executa o scraping usando a estratégia padrão

        O método delega para ``scrape_playwright_async`` reaproveitando
        os componentes de anti_bloqueio existentes.
        """
        from market_scraper.services import services_scraper_common as common

        return await common.scrape_playwright_async(url=url, **kwargs)
