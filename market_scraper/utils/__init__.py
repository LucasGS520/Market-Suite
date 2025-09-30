""" Utilitários e helpers usados em toda a aplicação de scraping

Reune somente funções puras e helpers específicos do ``market_scraper``
Controllers com estado (cookies, ritmo, circuito) residem em 
``market_scraper.utils_controllers`` para manter responsabilidades
isoladas. Para rotinas realmente compartilhadas entre serviços
consulte ``shared.utils`` diretamente.
"""

from ..utils_controllers.block_recovery import recover_html_if_blocked
from .requests_html_render import fetch_rendered_html


__all__ = ["recover_html_if_blocked", "fetch_rendered_html"]
