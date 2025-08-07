import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

#Alias para acessar utilitários e exceções usando o prefixo ``alert_app``
import utils
import market_alert.exceptions as alert_exceptions
sys.modules.setdefault("alert_app.utils", utils)
sys.modules.setdefault("alert_app.exceptions", alert_exceptions)
