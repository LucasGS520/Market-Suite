import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

#Alias para acessar utilitários e exceções usando prefixo ``market_alert``
from shared import utils
from shared import core as shared_core
from shared.core import config_base as shared_config_base

#Expõe o pacote ``shared.utils`` também como ``utils`` para compatibilidade
sys.modules.setdefault("utils", utils)
sys.modules.setdefault("core", shared_core)
sys.modules.setdefault("core.config_base", shared_config_base)

import market_alert.exceptions as alert_exceptions
sys.modules.setdefault("market_alert.utils", utils)
sys.modules.setdefault("market_alert.exceptions", alert_exceptions)
