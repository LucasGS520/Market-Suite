""" Atalho para o pacote principal de scraping """
from market_scraper import scraper_app as _scraper_app
import sys as _sys
_sys.modules[__name__] = _scraper_app
