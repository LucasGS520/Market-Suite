""" Pacote raiz do serviço MarketScraper """

import sys as _sys
import shared.utils as _utils

#Disponibiliza o pacote como ``scraper_app`` para compatibilidade
_sys.modules.setdefault("scraper_app", _sys.modules[__name__])
_sys.modules.setdefault("scraper_app.utils", _utils)

#Torna ``market_alert`` acessível caso o serviço de alertas esteja presente
try:
    import market_alert as _market_alert
    _sys.modules.setdefault("market_alert", _market_alert)
    _sys.modules.setdefault("market_alert.utils", _utils)

except Exception:
    pass
