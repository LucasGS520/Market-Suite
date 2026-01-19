""" Utilitários para calcular estabilidade e intervalos de coleta.

O cálculo considera o histórico de mudanças de preço e o tempo desde a última
alteração relevante, permitindo ajustar dinamicamente a frequência de coleta.
Este módulo é a única fonte de verdade para o cálculo de estabilidade e 
intervalos, evitando duplicação de lógica em outras partes do sistema.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta

from market_alert.core.config_alert import settings
from market_alert.models.models_products import MonitoredProduct


STABILITY_UNSTABLE = 0
STABILITY_STABLE = 1
STABILITY_VERY_STABLE = 2

def _normalize_datetime(value: datetime | None) -> datetime | None:
    """ Normaliza datas para UTC preservando valores nulos """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

def calculate_stability_score(
    product: MonitoredProduct,
    *,
    reference_time: datetime | None = None,
) -> int:
    """ Calcula a pontuação de estabilidade baseada na última mudança registrada """
    now = _normalize_datetime(reference_time) or datetime.now(timezone.utc)

    #Prioriza mudanças explícitas, mas considera métricas de grupo e criaão como fallback
    last_change = (
        product.last_price_change_at
        or product.group_collected_at
        or product.last_scraped_at
        or product.created_at
    )
    last_change = _normalize_datetime(last_change)

    if last_change is None:
        return STABILITY_UNSTABLE
    
    days_since_change = (now - last_change).total_seconds() / 86400

    if days_since_change >= settings.STABILITY_DAYS_VERY_STABLE:
        return STABILITY_VERY_STABLE
    if days_since_change >= settings.STABILITY_DAYS_STABLE:
        return STABILITY_STABLE
    return STABILITY_UNSTABLE

def _random_interval(min_seconds: int, max_seconds: int) -> int:
    """ Sorteia um intervalo entre limites """
    if min_seconds >= max_seconds:
        return min_seconds
    return random.randint(min_seconds, max_seconds)

def calculate_next_interval(
    product: MonitoredProduct,
    *,
    reference_time: datetime | None = None,
) -> int:
    """ Retorna o intervalo em segundos até a próxima coleta do produto """
    stability_score = calculate_stability_score(product, reference_time=reference_time)
    
    if stability_score == STABILITY_VERY_STABLE:
        return _random_interval(
            settings.COLLECT_INTERVAL_VERY_STABLE_MIN,
            settings.COLLECT_INTERVAL_VERY_STABLE_MAX
        )
    
    if stability_score == STABILITY_STABLE:
        return _random_interval(
            settings.COLLECT_INTERVAL_STABLE_MIN,
            settings.COLLECT_INTERVAL_STABLE_MAX,
        )
    
    return _random_interval(
        settings.COLLECT_INTERVAL_UNSTABLE_MIN,
        settings.COLLECT_INTERVAL_UNSTABLE_MAX,
    )

def calculate_next_check_at(
    product: MonitoredProduct,
    collected_at: datetime | None,
) -> datetime:
    """ Calcula o datetime da próxima coleta considerando o horário da extração """
    normalized_collected = _normalize_datetime(collected_at) or datetime.now(timezone.utc)
    interval_seconds = calculate_next_interval(product, reference_time=normalized_collected)
    return normalized_collected + timedelta(seconds=interval_seconds)
