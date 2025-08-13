""" Utilitários e helpers usados em toda a aplicação de scraping

Este pacote expõe apenas funcionalidades próprias do scraper.
Para rotinas compartilhadas utilize ``shared.utils`` diretamente
"""

from .playwright_client import PlaywrightClient, get_playwright_client
from .block_recovery import recover_html_if_blocked


__all__ = ["PlaywrightClient", "get_playwright_client", "recover_html_if_blocked"]
