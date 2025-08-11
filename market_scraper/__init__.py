""" Pacote raiz do serviço MarketScraper """

import sys as _sys

#Disponibiliza o pacote para importações diretas
_sys.modules.setdefault("market_scraper", _sys.modules[__name__])

#Torna ``market_alert`` acessível caso o serviço de alertas esteja presente
try:
    import market_alert as _market_alert
    _sys.modules.setdefault("market_alert", _market_alert)

except Exception:
    pass
