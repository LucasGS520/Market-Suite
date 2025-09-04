""" Utilitários e helpers usados em toda a aplicação de scraping

Este pacote expõe apenas funcionalidades próprias do scraper.
Para rotinas compartilhadas utilize ``shared.utils`` diretamente
"""

from .block_recovery import recover_html_if_blocked


__all__ = ["recover_html_if_blocked"]
