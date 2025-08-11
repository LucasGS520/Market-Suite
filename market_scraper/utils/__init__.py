""" Utilitários e helpers usados em toda a aplicação de scraping """

from .logging_utils import mask_identifier
from .playwright_client import PlaywrightClient, get_playwright_client
from .block_recovery import recover_html_if_blocked


__all__ = ["mask_identifier", "PlaywrightClient", "get_playwright_client", "recover_html_if_blocked"]
