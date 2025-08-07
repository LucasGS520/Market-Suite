""" Utilitários compartilhados entre os serviços """

#Permite que os utilitários sejam acessados via ``alert_app.utils`` e ``scraper_app.utils``
import sys as _sys

_sys.modules.setdefault("alert_app.utils", _sys.modules[__name__])
