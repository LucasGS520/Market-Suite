""" Utilitários para normalização de preços e decisões de histórico.

O módulo centraliza heurísticas usadas pelo collector e CRUDs para decidir
quando registrar histórico de preço e para remover valores inválidos como
``0``. A intenção é manter uma regra única de disponibilidade/preço em toda
suite, evitando gravações inconsistentes e facilitando auditoria.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

def normalize_scraped_price(value: Any) -> Decimal | None:
    """ Converte valores diversos para ``Decimal`` ignorando zeros.

    A conversão aceita inteiros, strings e ``Decimal``. Valores vazios ou
    iguais a zero são transformados em ``None`` para evitar histórico
    contaminado por preços inválidos.
    """
    if value in (None, "", 0, 0.0, "0", "0.0"):
        return None

    try:
        normalized = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None

    if normalized == 0:
        return None
    return normalized

def should_create_price_history(price: Decimal | None, availability: bool | None) -> bool:
    """ Indica se um ``PriceHistory`` deve ser criado.

    A regra considera indisponibilidade explícita ou ausência de preço como
    motivos para pular a criação de histórico, garantindo que o banco não
    receba valores nulos ou placeholders quando o anúncio está pausado ou
    removido.
    """
    if availability is False:
        return False
    return price is not None


__all__ = ["normalize_scraped_price", "should_create_price_history"]
