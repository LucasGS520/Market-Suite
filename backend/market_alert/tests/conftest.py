import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

#Importações diretas dos utilitários e exceções compartilhadas
from shared import utils
import shared.exceptions as alert_exceptions
