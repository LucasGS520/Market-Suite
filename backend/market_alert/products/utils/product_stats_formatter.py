""" Utilitários para formatar estatísticas derivadas de produtos monitorados """

from __future__ import annotations

from datetime import datetime
from enum import Enum

from market_alert.models.models_products import MonitoredProduct
from market_alert.products.utils.interval_calculator_products import (
    STABILITY_STABLE,
    STABILITY_UNSTABLE,
    STABILITY_VERY_STABLE,
)


class StabilityLevel(str, Enum):
    """ Enumeração legível de estabilidade para exposição na API """
    UNSTABLE = "unstable"
    STABLE = "stable"
    VERY_STABLE = "very_stable"

def format_stability_level(stability_score: int | None) -> str:
    """ Converte a pontuação de estabilidade para um nível textual legível """
    score = stability_score if stability_score is not None else STABILITY_UNSTABLE

    mapping = {
        STABILITY_UNSTABLE: StabilityLevel.UNSTABLE,
        STABILITY_STABLE: StabilityLevel.STABLE,
        STABILITY_VERY_STABLE: StabilityLevel.VERY_STABLE,
    }

    return mapping.get(score, StabilityLevel.UNSTABLE).value

def format_next_check_at(product: MonitoredProduct) -> datetime | None:
    """ Retorna a próxima coleta planejada preservando valores nulos """
    return product.next_check_at

def format_last_collected_at(product: MonitoredProduct) -> datetime | None:
    """ Retorna o timestamp da última coleta efetiva do monitorado """
    #Prioriza o instante real de coleta para evitar divergência com checagens administrativas
    return product.group_collected_at or product.collected_at

def get_product_stats(product: MonitoredProduct) -> dict:
    """ Retorna estatísticas derivadas do produto monitorado para a API """
    #Centraliza valores derivados para evitar divergências entre rotas e contratos
    return {
        "last_collected_at": format_last_collected_at(product),
        "last_price_change_at": product.last_price_change_at,
        "stability": format_stability_level(product.stability_score),
        "next_check_at": format_next_check_at(product),
        "monitored_since": product.created_at,
    }
