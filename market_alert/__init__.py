""" Pacote raiz do serviço MarketAlert """

import sys as _sys
import shared.utils as _utils

#Permite que o pacote seja acessado também como ``market_alert``
_sys.modules.setdefault("market_alert", _sys.modules[__name__])
_sys.modules.setdefault("market_alert.utils", _utils)
