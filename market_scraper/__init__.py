""" Pacote raiz do serviço MarketScraper

Este pacote pode ser utilizado de forma independente e não expõe
mais o módulo ``market_alert`` automaticamente.
"""

import sys as _sys

#Disponibiliza o pacote para importações diretas
_sys.modules.setdefault("market_scraper", _sys.modules[__name__])
