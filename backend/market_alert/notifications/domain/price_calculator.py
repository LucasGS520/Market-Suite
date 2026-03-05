""" Cálculo de delta de preço para avaliação de alertas.

Funções puras — sem I/O, sem efeitos colaterais.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def calculate_price_delta_percent(
    previous_price: Any,
    current_price: Any,
) -> Decimal | None:
    """ Calcula o percentual de variação entre dois preços.

    Args:
        previous_price: Preço anterior (qualquer tipo conversível para Decimal).
        current_price: Preço atual (qualquer tipo conversível para Decimal).

    Returns:
        Percentual de variação (positivo = aumento, negativo = queda).
        Retorna None se os valores forem inválidos ou o preço anterior for zero.
    """
    if previous_price is None or current_price is None:
        return None

    try:
        previous_value = Decimal(str(previous_price))
        current_value = Decimal(str(current_price))
    except (InvalidOperation, TypeError, ValueError):
        return None

    if previous_value == 0:
        return None

    return (current_value - previous_value) / previous_value * 100

def is_delta_below_threshold(
    previous_price: Any,
    current_price: Any,
    *,
    threshold_percent: Decimal,
) -> bool:
    """ Verifica se a variação de preço está abaixo do limiar mínimo configurado.

    Args:
        previous_price: Preço anterior.
        current_price: Preço atual.
        threshold_percent: Limiar mínimo de variação (em percentual).

    Returns:
        True se a variação for menor que o limiar (alerta deve ser suprimido).
        False se a variação atingiu o limiar (alerta deve prosseguir).
    """
    delta = calculate_price_delta_percent(previous_price, current_price)
    if delta is None:
        return False
    return abs(delta) < threshold_percent
