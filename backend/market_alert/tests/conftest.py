""" Configuração compartilhada de testes do market_alert """

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
#Incluímos raiz do repositório e backend no sys.path para resolver imports locais no pytest
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

#As variáveis são definidas aqui para garantir que o settings carregue em testes
os.environ.setdefault("DATABASE_URL", "postgresql://usuario:senha@localhost:5432/market_alert")
os.environ.setdefault("SECRET_KEY", "chave_teste_market_alert")

#Recarregamos o módulo de configuração para aplicar os valores acima
import market_alert.core.config_alert

importlib.reload(market_alert.core.config_alert)
