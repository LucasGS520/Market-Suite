""" Pacote raiz do serviço MarketScraper """

#Expõe ``scraper_app`` como pacote de nível superior
import sys as _sys
from . import scraper_app as _scraper_app
import utils as _utils

_sys.modules.setdefault("scraper_app", _scraper_app)

#Torna ``alert_app`` acessível se o pacote principal estiver disponível
try:
    from market_alert import alert_app as _alert_app
    _sys.modules.setdefault("alert_app", _alert_app)
    _sys.modules.setdefault("alert_app.utils", _utils)
except Exception:
    pass
