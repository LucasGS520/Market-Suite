""" Utilitários compartilhados entre os serviços """

#Permite que os utilitários sejam acessados via ``market_alert.utils`` e ``market_scraper.utils``
import sys as _sys

#Exponibiliza o pacote também como ``utils`` para retrocompatibilidade
_sys.modules.setdefault("utils", _sys.modules[__name__])
