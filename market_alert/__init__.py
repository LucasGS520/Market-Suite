""" Pacote raiz do serviço MarketAlert """

import sys as _sys
import shared.utils as _utils

#Permite que o pacote seja acessado também como ``alert_app``
_sys.modules.setdefault("alert_app", _sys.modules[__name__])
_sys.modules.setdefault("alert_app.utils", _utils)
