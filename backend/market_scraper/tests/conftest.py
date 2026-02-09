""" Configuração básica para resolver imports no pacote market_scraper """

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
#Mantemos raiz do repo e backend no sys.path para facilitar imports durante os testes
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))
