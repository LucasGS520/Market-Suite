""" Utilitários de normalização/comparação de preços com ``Decimal``. """

from __future__ import annotations
from decimal import Decimal, InvalidOperation


def to_decimal(value: Decimal | float | int | str | None) -> Decimal | None:
    """ Converte valores diversos para ``Decimal`` preservando ``None``.

    A normalização evita comparações inconsistentes quando preço chega como
    string ou float após coleta do scraper.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None

def different_prices(
    previous_price: Decimal | float | int | str | None,
    current_price: Decimal | float | int | str | None,
) -> bool:
    """ Compara preços após normalizar para ``Decimal``. """
    previous = to_decimal(previous_price)
    current = to_decimal(current_price)
    return previous != current
