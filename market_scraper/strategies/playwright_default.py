from __future__ import annotations

""" Estratégia padrão utilizando Playwright """

from typing import Any

from .base import ScrapingStrategy, register_strategy


class PlaywrightDefaultStrategy(ScrapingStrategy):
    """ Aplica o fluxo existente de scraping baseado em Playwright """

    priority = 100

    def supports_url(self, url: str) -> bool:
        """ Suporta qualquer URL por padrão """
        return True

    async def get_data(
        self,
        *,
        url: str,
        user_id: Any,
        payload: Any,
        product_type: str,
        rate_limiter: Any | None = None,
        circuit_breaker: Any | None = None,
        recovery_manager: Any | None = None,
    ) -> dict:
        """ Executa o scraping usando a estratégia padrão """
        from market_scraper.services import services_scraper_common as common

        #Utiliza o fluxo padrão baseado em Playwright
        return await common.scrape_playwright_async(
            url=url,
            user_id=user_id,
            payload=payload,
            product_type=product_type,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
            recovery_manager=recovery_manager,
        )

register_strategy(PlaywrightDefaultStrategy())
