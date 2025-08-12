""" Utilitários compartilhados entre os serviços """

#Permite que os utilitários sejam acessados via ``market_alert.utils`` e ``market_scraper.utils``
import sys as _sys

#Função reutilizável para anonimizar identificadores em registros de log
from .logging_utils import mask_identifier

#Exponibiliza o pacote também como ``utils`` para retrocombatibilidade
_sys.modules.setdefault("utils", _sys.modules[__name__])

#Define os simbolos exportados ao utilizar ``from shared.utils import *``
__all__ = ["mask_identifier"]
