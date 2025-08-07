""" Atalho para o pacote principal de alertas """
from market_alert import alert_app as _alert_app
import sys as _sys
_sys.modules[__name__] = _alert_app
