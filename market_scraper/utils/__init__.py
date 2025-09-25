""" Utilitários e helpers usados em toda a aplicação de scraping

Este pacote expõe apenas funcionalidades próprias do scraper.
Para rotinas compartilhadas utilize ``shared.utils`` diretamente
"""

from ..utils_controllers.block_recovery import recover_html_if_blocked
from .requests_html_render import fetch_rendered_html


__all__ = ["recover_html_if_blocked", "fetch_rendered_html"]
