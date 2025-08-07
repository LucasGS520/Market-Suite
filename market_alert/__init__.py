""" Pacote raiz do serviço MarketAlert """

#Expõe ``alert_app`` como pacote de nível superior
import sys as _sys
from . import alert_app as _alert_app
import utils as _utils

_sys.modules.setdefault("alert_app", _alert_app)
_sys.modules.setdefault("alert_app.utils", _utils)
