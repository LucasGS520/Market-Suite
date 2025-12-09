""" Wrapper utilitário para reutilizar o fluxo de comparação

O objetivo é permitir execução inline a partir de tasks de coleta
sem abrir novas sessões de banco, mantendo métricas e logs centralizados.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from market_alert.core.config_alert import settings
from market_alert.services.services_comparison import run_price_comparison


def run_comparison(db: Session, monitored_id: str | UUID) -> tuple[dict, list]:
    """ Executa a comparação de preços reutilizando a sessão existente """
    result, alerts = run_price_comparison(
        db,
        monitored_id,
        tolerance=Decimal(str(settings.PRICE_TOLERANCE)),
    )
    return result, alerts